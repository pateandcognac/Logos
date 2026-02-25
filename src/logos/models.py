# Logos/src/logos/models.py

"""
Wrappers for interacting with various ML / AI models.
This includes my core LLM intelligence and local vision models (YOLO).

Local models are loaded as lazy singletons to keep latency low while 
preventing unnecessary RAM/VRAM usage if they are never called.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import os

# Get Path to Python 3.11 interpreter (with Gemini SDK installed) from env var VENV_PY311
_PY311 = os.getenv("LOGOS_VENV_PY311", "/home/robot/robot_ws/.venv/bin/python3")

# The helper script will live next to this file as _llm_helper.py
WORKER_PATH = Path(__file__).with_name("_llm_helper.py")

# Lazy Singletons for Vision Models
_yolo11_model = None
_yolo_world_model = None

__all__ = ["llm", "yolo11", "yolo_world"]

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


def llm(prompt: str, model_alias: str = "fast", temperature: float = 0.7) -> str:
    """
    A simple, general-purpose wrapper to prompt my core LLM intelligence out-of-band.

    This function abstracts away the nuances of calling my own intelligence.
    It is text-only, stateless, and uses "instruct" style prompting.

    Args:
        prompt: The text prompt to send to the model.
        model_alias: choose from "smartest", "fast", or "fastest" (defaults to "fast").
        temperature: Sampling temperature (0.0–1.0).

    Returns:
        The text response from the model, or an empty string on error.
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
            timeout=120,
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


def yolo11(
    image: np.ndarray, 
    classes: Optional[List[str]] = None, 
    conf: float = 0.5
) -> List[Dict[str, Any]]:
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
        inside while loops for real-time tracking, person-following, or fast 
        obstacle classification during autonomous movement.
        
        Example:
            img = logos.vision.capture('pan_tilt').image
            people = logos.models.yolo11(img, classes=["person"])
            if people:
                logos.pantilt.look_at_pixel(people[0]["box_2d"][0:2]) # Look at top-left corner
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
    results = _yolo11_model.predict(source=image, conf=conf, classes=class_ids, verbose=False)
    
    return _normalize_yolo_boxes(
        result_boxes=results[0].boxes, 
        model_names=_yolo11_model.names, 
        img_h=img_h, 
        img_w=img_w, 
        source_name="yolo11"
    )


def yolo_world(
    image: np.ndarray, 
    prompts: List[str], 
    conf: float = 0.1
) -> List[Dict[str, Any]]:
    """
    Run inference using the YOLO-World open-vocabulary model.
    Can search for *anything* you describe in text.

    Args:
        image: A BGR uint8 numpy array.
        prompts: A list of descriptive strings to search for. 
                 (e.g., ["red backpack", "Mark's face", "coffee mug"]).
        conf: Minimum confidence threshold. Keep this lower (0.05-0.1) for 
              complex or novel prompts, as zero-shot confidence is generally lower.

    Returns:
        A list of detection dictionaries natively formatted for my context window.

    Note to self:
        This model is absolute magic for searching, but slightly slower than yolo11. 
        Use this when I am looking for a specific object that isn't in the standard 
        80 COCO classes, or when I want to filter by attributes (color, state).
        
        Example:
            img = logos.vision.capture('astra').image
            targets = logos.models.yolo_world(img, prompts=["blue toy block"], conf=0.05)
            if targets:
                logos.voice.speak("I found the blue block! 🟦")
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

    results = _yolo_world_model.predict(source=image, conf=conf, verbose=False)
    
    return _normalize_yolo_boxes(
        result_boxes=results[0].boxes, 
        model_names=_yolo_world_model.names, 
        img_h=img_h, 
        img_w=img_w, 
        source_name="yolo_world"
    )