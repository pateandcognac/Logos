# src/logos/models.py

"""
Wrappers for interacting with various ML / AI models.
This includes local vision models and text-only, stateless shortcut to my core LLM intelligence. 

Local models are loaded as lazy singletons to keep latency low while 
preventing unnecessary RAM/VRAM usage if they are never called.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
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
_yoloe_text_model = None
_yoloe_pf_model = None
_mp_hands_model = None

# Cache the last prompt sets so we do not re-encode text every frame
_yolo_world_prompt_key: Optional[Tuple[str, ...]] = None
_yoloe_text_prompt_key: Optional[Tuple[str, ...]] = None

# YOLOE defaults:
# 11s is my recommended starting point for on-robot latency.
_YOLOE_TEXT_WEIGHTS = "yoloe-11s-seg.pt"
_YOLOE_PROMPT_FREE_WEIGHTS = "yoloe-11s-seg-pf.pt"

__all__ = ["llm", "yolo11", "yolo_world", "yoloe", "hands"]

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
        return "ERROR"

    model_name = _llm_config.get("aliases", {}).get(
        model_alias,
        _llm_config.get("default_model", "gemini-flash-latest"),
    )

    if not WORKER_PATH.exists():
        print(f"Gemini worker script not found at {WORKER_PATH}")
        return "ERROR"

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
        return "ERROR"

    if proc.returncode != 0:
        print(
            f"Gemini worker failed with code {proc.returncode}. "
            f"Stderr:\n{proc.stderr}"
        )
        return "ERROR"

    try:
        data = json.loads(proc.stdout)
    except Exception as e:
        print(f"Failed to parse Gemini worker output: {e}\nRaw output:\n{proc.stdout!r}")
        return "ERROR"

    if "error" in data:
        print(f"Gemini worker returned error: {data.get('error')}")
        return "ERROR"

    text = data.get("text", "")
    if not isinstance(text, str):
        print(f"Gemini worker returned non-string text: {text!r}")
        return "ERROR"

    return text


# ─── YOLO Vision Models ────────────────────────────────────────────────

def _normalize_prompt_list(prompts: Optional[List[str]]) -> Tuple[str, ...]:
    """
    Clean prompt strings while preserving order.

    Returns:
        Tuple of non-empty prompt strings with surrounding whitespace removed.
    """
    if not prompts:
        return tuple()

    cleaned: List[str] = []
    for prompt in prompts:
        if prompt is None:
            continue
        text = str(prompt).strip()
        if text:
            cleaned.append(text)

    return tuple(cleaned)


def _get_model_label(
    model_names: Union[Dict[int, str], List[str], Tuple[str, ...]],
    cls_id: int,
) -> str:
    """
    Safely resolve a class ID into a human-readable label.

    Ultralytics model names are usually a dict, but some newer/open-vocab
    models may expose names in list-like form.
    """
    if isinstance(model_names, dict):
        return model_names.get(cls_id, str(cls_id))

    if isinstance(model_names, (list, tuple)):
        if 0 <= cls_id < len(model_names):
            return str(model_names[cls_id])

    return str(cls_id)


def _get_yoloe_constructor():
    """
    Return the most compatible Ultralytics constructor for YOLOE checkpoints.

    Prefer the dedicated YOLOE class when available. Fall back to YOLO so this
    wrapper remains usable on some mixed-version installs.
    """
    try:
        from ultralytics import YOLOE
        return YOLOE
    except ImportError:
        try:
            from ultralytics import YOLO
            return YOLO
        except ImportError:
            return None


def _get_yoloe_model(prompt_free: bool):
    """
    Lazy-load and return the requested YOLOE model instance.

    Args:
        prompt_free: If True, load the prompt-free checkpoint.
                     If False, load the text-prompt checkpoint.
    """
    global _yoloe_text_model, _yoloe_pf_model

    constructor = _get_yoloe_constructor()
    if constructor is None:
        print(
            "models: ultralytics package not installed, or this install does not "
            "expose YOLO/YOLOE. Cannot run YOLOE."
        )
        return None

    try:
        if prompt_free:
            if _yoloe_pf_model is None:
                _yoloe_pf_model = constructor(_YOLOE_PROMPT_FREE_WEIGHTS)
            return _yoloe_pf_model

        if _yoloe_text_model is None:
            _yoloe_text_model = constructor(_YOLOE_TEXT_WEIGHTS)
        return _yoloe_text_model

    except Exception as e:
        mode = "prompt-free" if prompt_free else "text-prompt"
        print(f"models: Failed to load YOLOE {mode} model: {e}")
        return None

def _coerce_image_input(image_or_result: Any) -> Tuple[np.ndarray, Optional[Any]]:
    """
    Return the ndarray from either a raw image or a CaptureResult-shaped object.

    I use a duck-typed check here instead of importing CaptureResult so this
    module stays lightweight and avoids tightening cross-module coupling.
    """
    if isinstance(image_or_result, np.ndarray):
        return image_or_result, None

    capture_image = getattr(image_or_result, "image", None)
    if isinstance(capture_image, np.ndarray):
        return capture_image, image_or_result

    raise TypeError(
        "models: expected a BGR np.ndarray or a CaptureResult-shaped object "
        "with an .image np.ndarray."
    )


def _with_capture_metadata(
    capture_result: Optional[Any],
    meta_key: str,
    detections: List[Dict[str, Any]],
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Any]]:
    """
    Attach detections to a CaptureResult-shaped input and preserve old ndarray behavior.

    Returns:
        If the input was raw image data, just the detection list.
        If the input was a CaptureResult, `(detections, capture_result)`.
    """
    if capture_result is None:
        return detections

    if hasattr(capture_result, "add_meta"):
        capture_result.add_meta(**{meta_key: detections})
    else:
        meta = getattr(capture_result, "meta", None)
        if isinstance(meta, dict):
            meta[meta_key] = detections

    return detections, capture_result


def _normalize_yolo_boxes(
    result_boxes: Any,
    model_names: Union[Dict[int, str], List[str], Tuple[str, ...]],
    img_h: int,
    img_w: int,
    source_name: str,
) -> List[Dict[str, Any]]:
    """Helper to convert Ultralytics pixel boxes to Logos 0-1000 normalized format."""
    formatted_results = []

    if result_boxes is None or len(result_boxes) == 0:
        return formatted_results

    for box in result_boxes:
        # box.xyxy[0] is [x_min, y_min, x_max, y_max] in pixels
        x1, y1, x2, y2 = box.xyxy[0].tolist()
        conf = float(box.conf[0])
        cls_id = int(box.cls[0])
        label = _get_model_label(model_names, cls_id)

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
            max(0, min(1000, norm_x2)),
        ]

        formatted_results.append({
            "label": label,
            "box_2d": box_2d,
            "confidence": round(conf, 2),
            "source": source_name,
        })

    return formatted_results


def yolo11(
    image: Any,
    classes: Union[List[str], None] = None,
    conf: float = 0.5,
    imgsz: int = 320,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Any]]:
    """
        Run inference using the blazing fast YOLO11 Nano model.
        Uses the standard 80 COCO classes (person, chair, cup, dog, etc).

        Args:
            image: A BGR uint8 numpy array or a CaptureResult from logos.vision.capture().
            classes: Optional list of specific class names to filter by (e.g., ["person"]).
                    If None, returns all detected classes.
            conf: Minimum confidence threshold (0.0 to 1.0).

        Returns:
            If image is an ndarray, a list of detection dictionaries:
            [{"label": "person", "box_2d": [y1, x1, y2, x2], "confidence": 0.88, "source": "yolo11"}]

            If image is a CaptureResult, returns `(detections, capture_result)`
            and annotates `capture_result.meta["det_yolo11"]`.

        Note to self:
            The fastest, yet dumbest, . Use this 
            inside loops for real-time tracking or fast obstacle classification.
            
            Example:
                # Capture the full result so we have metadata for latency compensation
                scene = logos.vision.capture('pan_tilt')
                people = logos.models.yolo11(scene.image, classes=["person"])
                
                if people:
                    # look_at handles the bounding box math and latency compensation automatically!
                    logos.skills.tracking.look_at(people[0], capture_result=scene)
    """
    global _yolo11_model
    image_array, capture_result = _coerce_image_input(image)
    
    try:
        from ultralytics import YOLO
    except ImportError:
        print("models: ultralytics package not installed. Cannot run YOLO11.")
        return _with_capture_metadata(capture_result, "det_yolo11", [])

    # Lazy-load singleton
    if _yolo11_model is None:
        # yolo11n.pt will automatically download to current dir if not present
        _yolo11_model = YOLO("yolo11n.pt") 

    img_h, img_w = image_array.shape[:2]
    
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
    results = _yolo11_model.predict(source=image_array, conf=conf, classes=class_ids, verbose=False, imgsz=imgsz)
    
    detections = _normalize_yolo_boxes(
        result_boxes=results[0].boxes, 
        model_names=_yolo11_model.names, 
        img_h=img_h, 
        img_w=img_w, 
        source_name="yolo11"
    )
    return _with_capture_metadata(capture_result, "det_yolo11", detections)


def yolo_world(
    image: Any,
    prompts: List[str],
    conf: float = 0.1,
    imgsz: int = 640
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Any]]:
    """
    Run inference using the YOLO-World open-vocabulary-ish model. Familiar with about 8000 common objects, concepts, attributes.

    Args:
        image: A BGR uint8 numpy array or a CaptureResult from logos.vision.capture().
        prompts: A list of descriptive strings to search for.
                 (e.g., ["grey backpack", "person wearing red shirt", "coffee mug"]).
        conf: Minimum confidence threshold. Keep this lower (0.05-0.1) for
              novel prompts, as zero-shot confidence is generally lower.

    Returns:
        If image is an ndarray, a list of detection dictionaries.
        If image is a CaptureResult, returns `(detections, capture_result)`
        and annotates `capture_result.meta["det_yolo_world"]`.

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
    global _yolo_world_model, _yolo_world_prompt_key
    image_array, capture_result = _coerce_image_input(image)

    try:
        from ultralytics import YOLO
    except ImportError:
        print("models: ultralytics package not installed. Cannot run YOLO-World.")
        return _with_capture_metadata(capture_result, "det_yolo_world", [])

    prompt_values = _normalize_prompt_list(prompts)
    if not prompt_values:
        print("models: yolo_world() requires at least one non-empty prompt.")
        return _with_capture_metadata(capture_result, "det_yolo_world", [])

    # Lazy-load singleton
    if _yolo_world_model is None:
        _yolo_world_model = YOLO("yolov8s-world.pt")

    img_h, img_w = image_array.shape[:2]

    # Only re-encode prompts if they changed
    prompt_key = tuple(p.lower() for p in prompt_values)
    if _yolo_world_prompt_key != prompt_key:
        _yolo_world_model.set_classes(list(prompt_values))
        _yolo_world_prompt_key = prompt_key

    results = _yolo_world_model.predict(
        source=image_array,
        conf=conf,
        verbose=False,
        imgsz=imgsz,
    )

    if not results:
        return _with_capture_metadata(capture_result, "det_yolo_world", [])

    detections = _normalize_yolo_boxes(
        result_boxes=results[0].boxes,
        model_names=_yolo_world_model.names,
        img_h=img_h,
        img_w=img_w,
        source_name="yolo_world",
    )
    return _with_capture_metadata(capture_result, "det_yolo_world", detections)

def yoloe(
    image: Any,
    prompts: Optional[List[str]] = None,
    conf: Optional[float] = None,
    imgsz: int = 640,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Any]]:
    """
    Run inference using YOLOE, my broad open-vocabulary detector. Can be prompted like yolo-world, or used in a prompt-free mode that returns detections from a huge built-in vocabulary.

    YOLOE has two useful modes:

    1) Prompt-free discovery mode:
       Leave `prompts=None` and I will use a prompt-free checkpoint with a
       large built-in vocabulary. This is good for asking:
           "What objects are in this scene?"

    2) Text-prompted search mode:
       Pass `prompts=["coffee mug", "charging cable", "person"]` and I will
       search specifically for those concepts.

    Args:
        image: A BGR uint8 numpy array or a CaptureResult from logos.vision.capture().
        prompts: Optional list of target class strings.
                 - None or [] -> prompt-free mode
                 - non-empty list -> text-prompted mode
        conf: Minimum confidence threshold.
              If None, a mode-specific default is used:
                  prompt-free: 0.20
                  text-prompted: 0.10
        imgsz: Inference image size. 640 is a good default.

    Returns:
        If image is an ndarray, a list of detection dictionaries:
        [
            {
                "label": "coffee mug",
                "box_2d": [y1, x1, y2, x2],
                "confidence": 0.74,
                "source": "yoloe_pf|yoloe_text"
            }
        ]

        If image is a CaptureResult, returns `(detections, capture_result)`
        and annotates `capture_result.meta["det_yoloe_pf"]` or
        `capture_result.meta["det_yoloe_text"]`.

    Note to self:
        This is my semantic wide-net.

        Use prompt-free mode when I want a rough inventory of what's present in a
        scene, especially when I do not know the exact class names ahead of time.

        Use text-prompted mode when I already know what I am hunting and want to
        narrow the model's attention.

        This wrapper keeps only bounding boxes, labels, and confidence so it stays
        compatible with my existing perception tooling. The underlying YOLOE
        checkpoints can also predict segmentation masks, but I am not surfacing
        them here yet.

        This is broader and usually heavier than a typical yolo classifier, so I should not use it as
        my default tight-loop tracker. A strong workflow is:
            1. yoloe(..., prompts=None)      # discover
            2. yoloe(..., prompts=[...])     # focus
            3. yolo11(...) or tracking loop  # fast follow-up

        Example:
            scene = logos.vision.capture("astra")
            discoveries = logos.models.yoloe(scene.image)

            mugs = logos.models.yoloe(
                scene.image,
                prompts=["coffee mug", "ceramic cup"],
                conf=0.08
            )

            if mugs:
                logos.vision.publish_debug(scene.image, mugs, source="yoloe")
    """
    global _yoloe_text_prompt_key
    image_array, capture_result = _coerce_image_input(image)

    prompt_values = _normalize_prompt_list(prompts)
    prompt_free = len(prompt_values) == 0
    source_name = "yoloe_pf" if prompt_free else "yoloe_text"
    meta_key = "det_" + source_name

    if conf is None:
        conf = 0.20 if prompt_free else 0.10

    model = _get_yoloe_model(prompt_free=prompt_free)
    if model is None:
        return _with_capture_metadata(capture_result, meta_key, [])

    if not prompt_free:
        prompt_key = tuple(p.lower() for p in prompt_values)
        if _yoloe_text_prompt_key != prompt_key:
            try:
                model.set_classes(list(prompt_values))
                _yoloe_text_prompt_key = prompt_key
            except Exception as e:
                print(f"models: Failed to set YOLOE text prompts: {e}")
                return _with_capture_metadata(capture_result, meta_key, [])

    img_h, img_w = image_array.shape[:2]

    try:
        results = model.predict(
            source=image_array,
            conf=float(conf),
            verbose=False,
            imgsz=imgsz,
        )
    except Exception as e:
        mode = "prompt-free" if prompt_free else "text-prompted"
        print(f"models: YOLOE {mode} inference failed: {e}")
        return _with_capture_metadata(capture_result, meta_key, [])

    if not results:
        return _with_capture_metadata(capture_result, meta_key, [])

    detections = _normalize_yolo_boxes(
        result_boxes=results[0].boxes,
        model_names=model.names,
        img_h=img_h,
        img_w=img_w,
        source_name=source_name,
    )
    return _with_capture_metadata(capture_result, meta_key, detections)

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

def hands(
    image: Any,
    max_hands: int = 2,
) -> Union[List[Dict[str, Any]], Tuple[List[Dict[str, Any]], Any]]:
    """
    Detect hands and interpret basic gestures using MediaPipe.
    
    Args:
        image: A BGR uint8 numpy array or a CaptureResult from logos.vision.capture().
        max_hands: Maximum number of hands to track.

    Returns:
        If image is an ndarray, a list of natively formatted detection dictionaries:
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

        If image is a CaptureResult, returns `(detections, capture_result)`
        and annotates `capture_result.meta["det_hands"]`.

    Note to self:
        This model is extremely fast. Use it to read human intent!
        Gestures recognized: 'open_palm', 'closed_fist', 'pointing', 'peace', 'unknown'.
        [y, x] coordinates are normalized 0-1000 for compatibility with existing tools.
    """
    global _mp_hands_model
    image_array, capture_result = _coerce_image_input(image)
    
    try:
        import mediapipe as mp
    except ImportError:
        print("models: mediapipe package not installed. Cannot run hand tracking.")
        return _with_capture_metadata(capture_result, "det_hands", [])

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
    rgb_image = image_array[:, :, ::-1] # Faster than cv2.cvtColor
    img_h, img_w = image_array.shape[:2]
    
    results = _mp_hands_model.process(rgb_image)
    
    formatted_results = []
    if not results.multi_hand_landmarks:
        return _with_capture_metadata(capture_result, "det_hands", formatted_results)

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

    return _with_capture_metadata(capture_result, "det_hands", formatted_results)
