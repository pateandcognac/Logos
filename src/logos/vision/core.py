# Logos/src/logos/vision/core.py

"""
Definitions and constants for my vision and actuation systems.
This module acts as the shared configuration hub for `logos.vision`.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Tuple, Optional

# --- Constants ---

# Image saving paths relative to workspace root
ARTIFACTS_DIR = "artifacts"

# Camera Names
CAM_PAN_TILT = "pan_tilt"
CAM_TOP_DOWN = "top_down"
CAM_ASTRA = "astra"

# Servo Limits (Raw Values) based on legacy calibration
# Note to self: These are hardware specific integers, not degrees.
PAN_SERVO_MIN = 150
PAN_SERVO_MAX = 600
PAN_SERVO_HOME = 400

TILT_SERVO_MIN = 225
TILT_SERVO_MAX = 550
TILT_SERVO_HOME = 400

# Full range of motion for the servos in degrees (approximate)
SERVO_FULL_RANGE_DEG = 180.0

# Calculated Conversion Factor: Servo counts per degree
# (600 - 150) / 180 = 2.5
SERVO_DEG_CONVERSION = (PAN_SERVO_MAX - PAN_SERVO_MIN) / SERVO_FULL_RANGE_DEG

# Degree Limits (Derived from legacy math)
# Pan: Left (-80) to Right (+100)
PAN_DEG_MIN = -80
PAN_DEG_MAX = 100

# Tilt: Down (-60) to Up (+70)
TILT_DEG_MIN = -60
TILT_DEG_MAX = 70


class CameraState(Enum):
    """Tracks the lifecycle of my cameras."""
    COLD = 0        # Device closed / Unsubscribed
    WARMING = 1     # Open/Subscribed, stabilizing exposure/wb
    HOT = 2         # Ready for immediate capture
    COOLDOWN = 3    # Idle but kept open briefly in case of follow-up


@dataclass
class ImageCapture:
    """
    Represents a single visual memory I have captured.
    
    Attributes:
        id: Unique base36 time-based ID.
        timestamp: Unix timestamp.
        paths: Dictionary of file paths (e.g., {'rgb': '...', 'depth': '...', 'meta': '...'}).
        camera_source: Name of the camera used.
        pan_tilt: Tuple of (pan, tilt) degrees at moment of capture.
    """
    id: str
    timestamp: float
    paths: dict
    camera_source: str
    pan_tilt: Tuple[int, int]