# src/skills/vision.py

"""
High-level visual perception and searching behaviors.

These skills combine my raw camera feeds with my ML models to find
objects and people in the environment.
"""

import time
import numpy as np
from typing import Any, Dict, List, Union
import logos

_COCO_CLASSES = {
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat",
    "traffic light", "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat",
    "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe", "backpack",
    "umbrella", "handbag", "tie", "suitcase", "frisbee", "skis", "snowboard", "sports ball",
    "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", "tennis racket",
    "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair",
    "couch", "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote",
    "keyboard", "cell phone", "microwave", "oven", "toaster", "sink", "refrigerator", "book",
    "clock", "vase", "scissors", "teddy bear", "hair drier", "toothbrush"
}

def smart_detect(
    image: np.ndarray, 
    targets: Union[str, List[str]], 
    conf: float = 0.25
) -> List[Dict[str, Any]]:
    """
    Intelligently route detection targets to the fastest, most capable of the YOLO models.

    Takes a target string or a mixed list of targets. Automatically sends standard
    objects to the blazing fast YOLO11 model, and descriptive/novel prompts 
    to the YOLO-World model.

    Args:
        image: A BGR uint8 numpy array.
        targets: A single string or a list of strings to search for.
                 (e.g. ["person", "chair", "blue backpack"]).
        conf: Minimum confidence threshold.

    Returns:
        A combined list of detection dictionaries from both models.
    """
    if isinstance(targets, str):
        targets = [targets]

    coco_targets = []
    world_targets = []

    for t in targets:
        if t.lower() in _COCO_CLASSES:
            coco_targets.append(t.lower())
        else:
            world_targets.append(t)

    all_detections = []

    # Fast path: standard COCO classes
    if coco_targets:
        coco_dets = logos.models.yolo11(image, classes=coco_targets, conf=conf)
        all_detections.extend(coco_dets)

    # Magic path: descriptive/open-vocabulary prompts
    if world_targets:
        # Lower confidence slightly for zero-shot prompts
        world_conf = max(0.05, conf - 0.15) 
        world_dets = logos.models.yolo_world(image, prompts=world_targets, conf=world_conf)
        all_detections.extend(world_dets)

    # Sort by confidence so the best matches are first
    all_detections.sort(key=lambda d: d.get("confidence", 0.0), reverse=True)
    
    return all_detections


def scan_room(
    targets: Union[str, List[str]], 
    sweep_type: str = "person", 
    looks_per_point: int = 3
) -> List[Dict[str, Any]]:
    """
    Perform a pan-tilt sweep to search the room for specific targets.

    Args:
        targets: Target string or list of strings to pass to smart_detect.
        sweep_type: "person" (4 horizontal points) or "object" (8 points, adding a downward row).
        looks_per_point: How many frames to capture and analyze at each stop. 
                         >1 helps overcome YOLO flicker/motion blur.

    Returns:
        The list of detections found at the first successful stop.
        Returns an empty list [] if nothing is found after the full sweep.
    """
    # Define our sweep patterns (pan_deg, tilt_deg)
    if sweep_type == "person":
        # 4 points: Level gaze, sweeping left to right
        base_points = [(100, 0), (40, 0), (-20, 0), (-80, 0)]
    else:
        # 8 points: Level gaze left to right, then looking down left to right
        base_points = [(100, 0), (40, 0), (-20, 0), (-80, 0), 
                  (-80, -60), (-20, -60), (40, -60), (100, -60)]

    # Prepend current position so we check where we are looking RIGHT NOW first
    curr_pan, curr_tilt = logos.pantilt.get_angles()
    points = [(curr_pan, curr_tilt)] + base_points

    for pan, tilt in points:
        # Move to the point. If we are already there (first point), this is near-instant.
        logos.pantilt.move(pan, tilt, duration=0.2)
        
        # MANDATORY: Let the camera and auto-exposure stabilize
        time.sleep(0.2) 

        for i in range(looks_per_point):
            # Capture a fresh frame
            img = logos.vision.capture('pan_tilt').image
            
            detections = smart_detect(img, targets)
            
            if detections:
                # Let Mark see our internal thoughts in RViz
                logos.vision.publish_debug(img, detections=detections, source="scan_room")
                return detections
            
            # Tiny delay if we are doing multiple 'looks'
            if i < looks_per_point - 1:
                time.sleep(0.1)

    # Return home if we found nothing
    logos.pantilt.home()
    return []