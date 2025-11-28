# Logos/src/logos/vision/intelligence.py

"""
The intelligence layer for my vision.
Wraps YOLO models to provide semantic understanding of images.
"""

from ultralytics import YOLO
import numpy as np
from typing import List, Dict, Any, Optional

# Default to the versatile World model which supports open-vocabulary
# DEFAULT_MODEL = "yolov8s-worldv2.pt"
DEFAULT_MODEL = "yoloe-11s-seg.pt"

class Brain:
    """Singleton wrapper for the vision model."""
    def __init__(self):
        self.model = None
        self.model_name = ""

    def load_model(self, model_name: str = DEFAULT_MODEL):
        if self.model is None or self.model_name != model_name:
            print(f"[Vision] Loading model: {model_name}...")
            self.model = YOLO(model_name)
            self.model_name = model_name
            # Force warm up? No, YOLO does that internally.

    def detect(self, image: np.ndarray, classes: Optional[List[str]] = None, conf: float = 0.25) -> List[Dict[str, Any]]:
        """
        Runs object detection on a numpy image.
        
        Args:
            image: BGR numpy array (OpenCV format).
            classes: List of text prompts for YOLO-World (e.g., ["red cup", "cat"]). 
                     If None, detects default COCO classes.
            conf: Confidence threshold.

        Returns:
            List of dictionaries:
            [{'label': 'person', 'conf': 0.9, 'box': [x1, y1, x2, y2]}, ...]
        """
        self.load_model()
        
        if classes:
            # For YOLO-World, we set the classes dynamically
            self.model.set_classes(classes)
        
        # Run inference
        results = self.model.predict(image, conf=conf, verbose=False)
        
        detections = []
        result = results[0] # We only process one image at a time
        
        for box in result.boxes:
            # box.xyxy is [x1, y1, x2, y2]
            coords = box.xyxy[0].tolist()
            confidence = float(box.conf[0])
            class_id = int(box.cls[0])
            
            # Get label
            if result.names:
                label = result.names[class_id]
            else:
                label = str(class_id)

            detections.append({
                "label": label,
                "conf": round(confidence, 3),
                "box": [int(c) for c in coords]
            })
            
        return detections

_brain = Brain()

def detect_objects(image: np.ndarray, classes: List[str] = None) -> List[Dict[str, Any]]:
    """Helper function to run detection quickly."""
    return _brain.detect(image, classes)