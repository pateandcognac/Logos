# Logos/src/logos/vision/__init__.py

"""
My Vision System. 👁️
This API allows me to see the world, move my head, and interpret visual data.
"""

import cv2
import time
from pathlib import Path
from typing import Optional, List
from .core import (
    ImageCapture, 
    CAM_PAN_TILT, CAM_TOP_DOWN, CAM_ASTRA
)
from .utils import make_photo_id, get_artifact_path
from .cameras import get_camera
from . import actuators
from . import intelligence
from ..core import api_call, Verbosity
from ..utils import dump_llm_yaml

# Expose actuator functions directly
look_at = actuators.look_at
look_home = actuators.look_home
laser = actuators.laser
set_flash = actuators.set_flash
set_face_leds = actuators.set_face_leds
set_heart_light = actuators.set_heart_light

@api_call(default_verbosity=Verbosity.BRIEF)
def capture(
    camera_name: str = CAM_PAN_TILT,
    caption: str = "",
    detect: bool = False,
    detect_classes: Optional[List[str]] = None
) -> Optional[ImageCapture]:
    """
    Captures an image from the specified camera, saves it, and makes it available to my context.

    Args:
        camera_name: 'pan_tilt', 'top_down', or 'astra'.
        caption: Optional text describing what I am looking for/at.
        detect: If True, runs YOLO detection on the image before saving metadata.
        detect_classes: Optional list of specific objects to look for (e.g., ["mug", "pen"]).

    Returns:
        An ImageCapture object containing paths and metadata, or None if failed.

    Note to self:
        This function automatically prints the <file> tag to stdout.
        I can access the return object to do further processing in Python.
    """
    # 1. Acquire Image
    try:
        cam = get_camera(camera_name)
        rgb, depth = cam.get_latest_frame()
    except Exception as e:
        print(f"Vision Error: Could not access {camera_name} - {e}")
        return None

    if rgb is None:
        print(f"Vision Error: Timeout waiting for {camera_name}.")
        return None

    # 2. Generate ID and Paths
    photo_id = make_photo_id()
    path_rgb = get_artifact_path(camera_name, photo_id, ".jpg")
    path_depth = get_artifact_path(camera_name, photo_id, "_depth.png")
    path_meta = get_artifact_path(camera_name, photo_id, ".yaml")

    paths = {"rgb": str(path_rgb)}

    # 3. Save Images
    cv2.imwrite(str(path_rgb), rgb)
    
    if depth is not None:
        # Save depth as 16-bit PNG (standard for depth)
        cv2.imwrite(str(path_depth), depth)
        paths["depth"] = str(path_depth)

    # 4. Intelligence (Optional)
    detections = []
    if detect:
        detections = intelligence.detect_objects(rgb, classes=detect_classes)

    # 5. Metadata Construction
    # Get current physical state
    pan_servo = actuators._actuators.current_pan_servo
    tilt_servo = actuators._actuators.current_tilt_servo
    
    meta_data = {
        "id": photo_id,
        "timestamp": time.time(),
        "camera": camera_name,
        "caption": caption,
        "state": {
            "pan_servo": pan_servo,
            "tilt_servo": tilt_servo,
            # We could add "robot_pose" here later if we hook into TF
        },
        "detections": detections,
        "files": paths
    }

    # 6. Save Metadata
    with open(path_meta, 'w') as f:
        f.write(dump_llm_yaml(meta_data))
    paths["meta"] = str(path_meta)

    # 7. Context Output
    # This ensures I see it immediately.
    print(f"<file path=\"{path_rgb}\">{caption}</file>")
    if detect and detections:
        # Summarize detections briefly
        labels = [d['label'] for d in detections]
        print(f"System Note: Detected {', '.join(labels)}")

    return ImageCapture(
        id=photo_id,
        timestamp=meta_data['timestamp'],
        paths=paths,
        camera_source=camera_name,
        pan_tilt=(0,0) # Todo: Reverse map servo to degrees for this object if needed
    )