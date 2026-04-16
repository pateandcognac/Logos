# Logos/src/logos/models.py

"""
Wrappers for interacting with various ML / AI models.
This includes local vision models and text-only, stateless shortcut to my core LLM intelligence. 

Local models are loaded as lazy singletons to keep latency low while 
preventing unnecessary RAM/VRAM usage if they are never called.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import numpy as np
import os
import math

# Get Path to Python 3.11 interpreter (with Gemini SDK installed) from env var VENV_PY311
_PY311 = os.getenv("LOGOS_VENV_PY311", "/home/robot/robot_ws/.venv/bin/python3")

# The helper script will live next to this file as _llm_helper.py
WORKER_PATH = Path(__file__).with_name("_llm_helper.py")

# Lazy Singletons for Vision Models
_yolo11_model = None
_yolo_world_model = None
_mp_hands_model = None

__all__ = ["llm", "yolo11", "yolo_world", "hands"]

_llm_config: Dict[str, Any] = {}

# ─── My LLM Intelligence ──────────────────────────────────────────────────

def _initialize_llm() -> None:
    """
    Loads model alias config from .system/framework_config.json.

    We deliberately do NOT import the Gemini SDK here. The actual LLM
    interaction happens in the 3.11 worker script.
    """
    global _llm_config
    if _llm_config:
        return

    config_path = Path.cwd() / ".system" / "framework_config.json"

    try:
        with config_path.open("r") as f:
            framework_config = json.load(f)

        aliases = framework_config.get("llm_tool_models", {}).get("aliases", {})
        _llm_config["aliases"] = aliases
        # Default to the 'fast' model if it exists, otherwise a sensible fallback.
        # Choose: smartest, fast, fastest
        _llm_config["default_model"] = aliases.get("fast", "gemini-flash-latest")
    except Exception as e:
        print(f"Error initializing LLM config from {config_path}: {e}")
        _llm_config = {}


def llm(prompt: str, model_alias: str = "fast", temperature: float = 1.0) -> str:
    """
    A simple wrapper to prompt my core, stateless, LLM intelligence out-of-band. 

    This function abstracts away the nuances of calling my own intelligence.
    It does *NOT* have an existing system prompt, context of my identity as
    Logos, or tools. It is text-only, stateless, and uses "instruct" style prompting.

    Args:
        prompt: The text prompt to send to the model.
        model_alias: choose from "smartest", "fast", or "fastest" (defaults to "fast").
        temperature: 1.0 is recommended for best reasoning!

    Returns:
        The text response from the model, or an empty string on error.

    Note to self:
        ⚠️ AMNESIA WARNING: This model is completely stateless! It does NOT know 
        it is Logos, it has no access to my `logos` API tools, and it cannot see 
        my hooks or palimpsest. 
        
        If I use this to summarize text, extract data, or format strings, I must 
        pass ALL necessary context directly inside the `prompt` string.
    """
    if not _llm_config:
        _initialize_llm()

    if not _llm_config:
        print("LLM config not available.")
        return ""

    model_name = _llm_config.get("aliases", {}).get(
        model_alias,
        _llm_config.get("default_model", "gemini-flash-latest"),
    )

    if not WORKER_PATH.exists():
        print(f"Gemini worker script not found at {WORKER_PATH}")
        return ""

    payload = {
        "prompt": prompt,
        "model_name": model_name,
        "temperature": float(temperature),
    }

    try:
        proc = subprocess.run(
            [_PY311, str(WORKER_PATH)],
            input=json.dumps(payload),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180,
        )
    except Exception as e:
        print(f"Error invoking Gemini worker: {e}")
        return ""

    if proc.returncode != 0:
        print(
            f"Gemini worker failed with code {proc.returncode}. "
            f"Stderr:\n{proc.stderr}"
        )
        return ""

    try:
        data = json.loads(proc.stdout)
    except Exception as e:
        print(f"Failed to parse Gemini worker output: {e}\nRaw output:\n{proc.stdout!r}")
        return ""

    if "error" in data:
        print(f"Gemini worker returned error: {data.get('error')}")
        return ""

    text = data.get("text", "")
    if not isinstance(text, str):
        print(f"Gemini worker returned non-string text: {text!r}")
        return ""

    return text


# ─── YOLO Vision Models ────────────────────────────────────────────────

def _normalize_yolo_boxes(
    result_boxes: Any, 
    model_names: Dict[int, str], 
    img_h: int, 
    img_w: int, 
    source_name: str
) -> List[Dict[str, Any]]:
    """Helper to convert ultralytics pixel boxes to Logos 0-1000 normalized format."""
    formatted_results = []
    
    if result_boxes is None or len(result_boxes) == 0:
        return formatted_results

    for box in result_boxes:
        # box.xyxy[0] is [x_min, y_min, x_max, y_max] in pixels
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])
        cls_id = int(box.cls[0])
        label = model_names[cls_id]

        # Convert to Logos format: [y_min, x_min, y_max, x_max] mapped to 0-1000
        norm_y1 = int((y1 / img_h) * 1000)
        norm_x1 = int((x1 / img_w) * 1000)
        norm_y2 = int((y2 / img_h) * 1000)
        norm_x2 = int((x2 / img_w) * 1000)

        # Clamp to 0-1000 bounds
        box_2d = [
            max(0, min(1000, norm_y1)),
            max(0, min(1000, norm_x1)),
            max(0, min(1000, norm_y2)),
            max(0, min(1000, norm_x2))
        ]

        formatted_results.append({
            "label": label,
            "box_2d": box_2d,
            "confidence": round(conf, 2),
            "source": source_name
        })

    return formatted_results


def yolo11(image: np.ndarray, classes: Union[List[str], None] = None, conf: float = 0.5, imgsz: int = 320) -> List[Dict[str, Any]]:
    """
        Run inference using the blazing fast YOLO11 Nano model.
        Uses the standard 80 COCO classes (person, chair, cup, dog, etc).

        Args:
            image: A BGR uint8 numpy array (like from logos.vision.capture().image).
            classes: Optional list of specific class names to filter by (e.g., ["person"]).
                    If None, returns all detected classes.
            conf: Minimum confidence threshold (0.0 to 1.0).

        Returns:
            A list of detection dictionaries natively formatted for my context window:
            [{"label": "person", "box_2d": [y1, x1, y2, x2], "confidence": 0.88, "source": "yolo11"}]

        Note to self:
            This is my peripheral nervous system! It is incredibly fast. Use this 
            inside loops for real-time tracking or fast obstacle classification.
            
            Example:
                img = logos.vision.capture('pan_tilt').image
                people = logos.models.yolo11(img, classes=["person"])
                if people:
                    # Use utils.get_center to find the middle of the bounding box
                    target_center = logos.utils.get_center(people[0]["box_2d"])
                    logos.pantilt.look_at_pixel(target_center)
    """
    global _yolo11_model
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("models: ultralytics package not installed. Cannot run YOLO11.")
        return []

    # Lazy-load singleton
    if _yolo11_model is None:
        # yolo11n.pt will automatically download to current dir if not present
        _yolo11_model = YOLO("yolo11n.pt") 

    img_h, img_w = image.shape[:2]
    
    # Map requested string classes to integer IDs for filtering
    class_ids = None
    if classes:
        class_ids = []
        for c in classes:
            # Find the ID for the requested string
            for k, v in _yolo11_model.names.items():
                if v.lower() == c.lower():
                    class_ids.append(k)

    # Run inference (verbose=False keeps stdout clean)
    results = _yolo11_model.predict(source=image, conf=conf, classes=class_ids, verbose=False, imgsz=imgsz)
    
    return _normalize_yolo_boxes(
        result_boxes=results[0].boxes, 
        model_names=_yolo11_model.names, 
        img_h=img_h, 
        img_w=img_w, 
        source_name="yolo11"
    )


def yolo_world(
    image: np.ndarray, 
    prompts: List[str] = None, 
    conf: float = 0.5,
    imgsz: int = 640
) -> List[Dict[str, Any]]:
    """
    Run inference using the YOLO-World open-vocabulary-ish model. Familiar with about 8000 common objects, concepts, attributes.

    Args:
        image: A BGR uint8 numpy array.
        prompts: An optional list of descriptive strings to search for. 
                 (e.g., ["grey backpack", "person wearing red shirt", "coffee mug"]).
        conf: Minimum confidence threshold. Keep this lower (0.05-0.1) for 
              novel prompts, as zero-shot confidence is generally lower.

    Returns:
        A list of detection dictionaries natively formatted for my context window.

    Note to self:
        This model is absolute magic for searching, but slower than yolo11. 
        Use this when I am looking for a specific object that isn't in the standard 
        80 COCO classes, or when I want to filter by attributes (color, state).
        
        Example:
            img = logos.vision.capture('astra').image
            targets = logos.models.yolo_world(img, prompts=["blue toy block"], conf=0.05)
            if targets:
                logos.emote.ttp("I found the blue block! 🟦")
    """
    global _yolo_world_model
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("models: ultralytics package not installed. Cannot run YOLO-World.")
        return []

    # Lazy-load singleton
    if _yolo_world_model is None:
        _yolo_world_model = YOLO("yolov8s-world.pt")

    img_h, img_w = image.shape[:2]

    # YOLO-World requires setting the custom classes before inference
    _yolo_world_model.set_classes(prompts)

    results = _yolo_world_model.predict(source=image, conf=conf, verbose=False, imgsz=imgsz)
    
    return _normalize_yolo_boxes(
        result_boxes=results[0].boxes, 
        model_names=_yolo_world_model.names, 
        img_h=img_h, 
        img_w=img_w, 
        source_name="yolo_world"
    )

# ─── MediaPipe Hands ──────────────────────────────────────────────────

def _recognize_gesture(landmarks: List[List[int]]) -> str:
    """
    A lightweight, math-based heuristic to recognize basic hand gestures.
    Calculates if a finger is 'open' by checking if its tip is further 
    from the wrist (landmark 0) than its PIP joint.
    """
    def dist(i, j):
        return math.hypot(landmarks[i][0] - landmarks[j][0], landmarks[i][1] - landmarks[j][1])
    
    # Finger indices: [Tip, PIP]
    # Thumb uses MCP (2) instead of PIP for better distance heuristics
    fingers_open = {
        "thumb": dist(4, 0) > dist(2, 0), 
        "index": dist(8, 0) > dist(6, 0),
        "middle": dist(12, 0) > dist(10, 0),
        "ring": dist(16, 0) > dist(14, 0),
        "pinky": dist(20, 0) > dist(18, 0),
    }
    
    opens = sum(fingers_open.values())
    
    if opens == 5: return "open_palm"
    if opens == 0: return "closed_fist"
    if fingers_open["index"] and not fingers_open["middle"] and not fingers_open["ring"] and not fingers_open["pinky"]:
        return "pointing"
    if fingers_open["index"] and fingers_open["middle"] and not fingers_open["ring"] and not fingers_open["pinky"]:
        return "peace"
        
    return "unknown"

def hands(image: np.ndarray, max_hands: int = 2) -> List[Dict[str, Any]]:
    """
    Detect hands and interpret basic gestures using MediaPipe.
    
    Args:
        image: A BGR uint8 numpy array.
        max_hands: Maximum number of hands to track.

    Returns:
        A list of natively formatted detection dictionaries:
        [
            {
                "handedness": "Right", 
                "confidence": 0.98,
                "gesture": "open_palm|closed_fist|pointing|peace|unknown",
                "box_2d": [y_min, x_min, y_max, x_max], 
                "center_2d": [y, x],
                "landmarks": [[y, x], [y, x], ...] # 21 points
            }
        ]

    Note to self:
        This model is extremely fast. Use it to read human intent!
        Gestures recognized: 'open_palm', 'closed_fist', 'pointing', 'peace', 'unknown'.
        [y, x] coordinates are normalized 0-1000 for compatibility with existing tools.
    """
    global _mp_hands_model
    
    try:
        import mediapipe as mp
    except ImportError:
        print("models: mediapipe package not installed. Cannot run hand tracking.")
        return []

    # Lazy-load singleton
    if _mp_hands_model is None:
        # static_image_mode=True forces it to treat each frame independently, 
        # which is safer for us since we might call this sporadically rather than at 30fps.
        _mp_hands_model = mp.solutions.hands.Hands(
            static_image_mode=True, 
            max_num_hands=max_hands,
            min_detection_confidence=0.5
        )

    # MediaPipe expects RGB
    rgb_image = image[:, :, ::-1] # Faster than cv2.cvtColor
    img_h, img_w = image.shape[:2]
    
    results = _mp_hands_model.process(rgb_image)
    
    formatted_results = []
    if not results.multi_hand_landmarks:
        return formatted_results

    for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
        # Convert normalized 0.0-1.0 floats to Logos 0-1000 [y, x] integers
        landmarks_0_1000 = []
        y_coords = []
        x_coords = []
        
        for lm in hand_landmarks.landmark:
            norm_y = int(lm.y * 1000)
            norm_x = int(lm.x * 1000)
            # Clamp just in case the bounding box goes slightly off-screen
            norm_y = max(0, min(1000, norm_y))
            norm_x = max(0, min(1000, norm_x))
            
            landmarks_0_1000.append([norm_y, norm_x])
            y_coords.append(norm_y)
            x_coords.append(norm_x)
            
        # Derive 2D Box and Center from the landmarks
        box_2d = [min(y_coords), min(x_coords), max(y_coords), max(x_coords)]
        center_2d = [
            int((box_2d[0] + box_2d[2]) / 2),
            int((box_2d[1] + box_2d[3]) / 2)
        ]
        
        # Interpret Gesture
        gesture_label = _recognize_gesture(landmarks_0_1000)
        
        formatted_results.append({
            "handedness": handedness.classification[0].label,
            "confidence": round(float(handedness.classification[0].score), 2),
            "gesture": gesture_label,
            "box_2d": box_2d,
            "center_2d": center_2d,
            "landmarks": landmarks_0_1000
        })

    return formatted_results