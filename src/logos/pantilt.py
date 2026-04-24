# src/logos/pantilt.py

"""
Control for the pan/tilt mechanism that orients my camera gaze and laser pointer.

The pan/tilt mechanism is my directed gaze — it carries my high-res webcam,
illuminator LEDs, and laser pointer. This module translates between intuitive
degree-space commands and the raw servo protocol spoken by the Arduino.

Coordinate convention (from my perspective, facing forward):
    Pan:  positive = left,  negative = right
    Tilt: positive = up,    negative = down
    Home: (0, 0) = straight ahead, level

Physical limits:
    Pan:  +100° (left)  to -80° (right)
    Tilt: -60° (down)  to  +70° (up)
"""

import time
import threading
import rospy
from std_msgs.msg import Int32
from .core import api_call, Verbosity, check_for_interrupt
from typing import Dict, Optional, Tuple


__all__ = [
    "move", "nudge", "home", "get_angles",
    "PAN_RANGE", "TILT_RANGE", "HOME", "FOV",
]



# ─── Servo Constants (internal) ──────────────────────────────────────
# These define the mapping between degrees and raw servo pulse counts.
# The Arduino expects raw counts on the /pan_tilt/move/* topics.

_SERVO_MIN = 150
_SERVO_MAX = 600
_FULL_RANGE_DEG = 180.0  # Degrees swept across full servo range

# Conversion factor: servo counts per degree
_COUNTS_PER_DEG = (_SERVO_MAX - _SERVO_MIN) / _FULL_RANGE_DEG  # 2.5

# Home positions in servo counts (0° in degree space)
_HOME_PAN_COUNTS = 400
_HOME_TILT_COUNTS = 450

# Physical servo limits for the tilt axis (narrower than full range)
_TILT_SERVO_MIN = 225
_TILT_SERVO_MAX = 550

# ─── Public Constants ────────────────────────────────────────────────

# Degree limits derived from servo limits:
#   deg = (home_counts - servo_counts) / counts_per_deg
PAN_RANGE = (-100.0, 80.0)    # (right_limit, left_limit) 
TILT_RANGE = (-60.0, 70.0)    # (down_limit, up_limit)
HOME = (0.0, 0.0)

# Camera FOV in degrees (horizontal, vertical)
# Defined per source camera. Astra included for future cross-camera gaze.
FOV: Dict[str, Tuple[float, float]] = {
    "pan_tilt":    (65.0, 50.0),
    "top_down":    (65.0, 50.0),
    "astra_rgb":   (63.0, 49.0),
    "astra_depth": (58.0, 45.0),
}


# ─── Internal Conversion ─────────────────────────────────────────────

def _counts_to_deg_pan(counts: int, home_counts: int) -> float:
    return (counts - home_counts) / _COUNTS_PER_DEG

def _deg_to_counts_pan(deg: float, home_counts: int) -> int:
    # +deg (Left) equals higher servo counts
    return int(round(home_counts + deg * _COUNTS_PER_DEG))

def _deg_to_counts_tilt(deg: float, home_counts: int) -> int:
    # +deg (Up) equals lower servo counts
    return int(round(home_counts - deg * _COUNTS_PER_DEG))

def _counts_to_deg_tilt(counts: int, home_counts: int) -> float:
    return (home_counts - counts) / _COUNTS_PER_DEG

def _clamp_deg(pan_deg: float, tilt_deg: float) -> Tuple[float, float]:
    """Clamp pan and tilt to their physical limits. Returns (pan, tilt)."""
    pan = max(PAN_RANGE[0], min(PAN_RANGE[1], pan_deg))
    tilt = max(TILT_RANGE[0], min(TILT_RANGE[1], tilt_deg))
    return (pan, tilt)


# ─── ROS Interface (internal) ────────────────────────────────────────

_pan_pub: Optional[rospy.Publisher] = None
_tilt_pub: Optional[rospy.Publisher] = None

# Current position tracking from Arduino feedback
_current_pan_counts: int = _HOME_PAN_COUNTS
_current_tilt_counts: int = _HOME_TILT_COUNTS
_position_lock = threading.Lock()
_subscribers_initialized = False


def _ensure_publishers():
    """Lazily create ROS publishers for servo commands."""
    global _pan_pub, _tilt_pub
    if _pan_pub is None:
        _pan_pub = rospy.Publisher(
            "/pan_tilt/move/pan", Int32, queue_size=10
        )
    if _tilt_pub is None:
        _tilt_pub = rospy.Publisher(
            "/pan_tilt/move/tilt", Int32, queue_size=10
        )


def _ensure_subscribers():
    """Lazily subscribe to servo position feedback topics."""
    global _subscribers_initialized
    if _subscribers_initialized:
        return
    rospy.Subscriber("/pan_tilt/pan_pos", Int32, _pan_pos_cb, queue_size=1)
    rospy.Subscriber("/pan_tilt/tilt_pos", Int32, _tilt_pos_cb, queue_size=1)
    _subscribers_initialized = True


def _pan_pos_cb(msg):
    global _current_pan_counts
    with _position_lock:
        _current_pan_counts = msg.data


def _tilt_pos_cb(msg):
    global _current_tilt_counts
    with _position_lock:
        _current_tilt_counts = msg.data


def _publish_servo(pan_counts: int, tilt_counts: int, repeat: int = 1):
    """
    Send servo commands to the Arduino.
    
    Args:
        repeat: Number of times to publish. We use >1 for 'insurance' 
                on final destination moves.
    """
    _ensure_publishers()
    for i in range(repeat):
        _pan_pub.publish(Int32(data=pan_counts))
        _tilt_pub.publish(Int32(data=tilt_counts))
        if i < repeat - 1:
            time.sleep(0.01) # Very brief gap if repeating


# ─── Public API ───────────────────────────────────────────────────────

@api_call(default_verbosity=Verbosity.BRIEF)
def move(
    pan_deg: float, 
    tilt_deg: float, 
    duration: float = 0.25, 
    steps: int = 5
) -> Tuple[float, float]:
    """
    Move the pan/tilt head to an absolute position with interpolation and easing. Blocking.

    Args:
        pan_deg: Target pan.
        tilt_deg: Target tilt.
        duration: Total time for the movement in seconds.
        steps: Number of intermediate points. Set to 0 or 1 for immediate jumps.

    Returns:
        The clamped (pan, tilt) degrees actually commanded.

    Note to self:
        Interpolation attempts to solve three problems: cheap servos sometimes getting stuck, the arduino missing a message, and easing camera shake. By breaking it into smaller steps, it makes my movements look more natural, prevents hardware-straining 'snaps', and reduces camera shake by easing in quadratically.
    """
    _ensure_subscribers()
    target_pan, target_tilt = _clamp_deg(pan_deg, tilt_deg)
    
    # Get our current starting point
    start_pan, start_tilt = get_angles()
    
    # Calculate deltas
    d_pan = target_pan - start_pan
    d_tilt = target_tilt - start_tilt

    # Immediate jump if no duration/steps requested
    if duration <= 0 or steps <= 1:
        p_cnt = _deg_to_counts_pan(target_pan, _HOME_PAN_COUNTS)
        t_cnt = _deg_to_counts_tilt(target_tilt, _HOME_TILT_COUNTS)
        _publish_servo(p_cnt, t_cnt, repeat=1)
        return (target_pan, target_tilt)

    step_delay = duration / steps

    for i in range(1, steps + 1):
        check_for_interrupt()
        
        # Normalized time (0.0 to 1.0)
        t = i / steps
        
        # Quadratic Out Easing: f(t) = 1 - (1-t)^2
        # This gives us a linear start and a soft deceleration at the end.
        ease_t = 1 - (1 - t) * (1 - t)
        
        curr_pan = start_pan + (d_pan * ease_t)
        curr_tilt = start_tilt + (d_tilt * ease_t)
        
        p_cnt = _deg_to_counts_pan(curr_pan, _HOME_PAN_COUNTS)
        t_cnt = _deg_to_counts_tilt(curr_tilt, _HOME_TILT_COUNTS)
        
        # Publish current step (no repeat needed during interpolation)
        _publish_servo(p_cnt, t_cnt, repeat=1)
        
        time.sleep(step_delay)

    # Final "Insurance" publish to ensure we are exactly at the target
    final_p = _deg_to_counts_pan(target_pan, _HOME_PAN_COUNTS)
    final_t = _deg_to_counts_tilt(target_tilt, _HOME_TILT_COUNTS)
    _publish_servo(final_p, final_t, repeat=1)
    
    return (target_pan, target_tilt)


@api_call(default_verbosity=Verbosity.BRIEF)
def nudge(pan_deg: float, tilt_deg: float) -> Tuple[float, float]:
    """
    Adjust the pan/tilt head by a relative offset from its current position.

    Args:
        pan_deg:  Degrees to add to current pan. Positive = leftward.
        tilt_deg: Degrees to add to current tilt. Positive = upward.

    Returns:
        The new absolute (pan, tilt) position in degrees after clamping.

    Note to self:
        Handy for small corrections without needing to know absolute position.
            logos.pantilt.nudge(5, 0)    # Glance a bit more to the left
            logos.pantilt.nudge(0, -10)  # Tilt down a touch
    """
    current_pan, current_tilt = get_angles()
    new_pan = current_pan + pan_deg
    new_tilt = current_tilt + tilt_deg
    return move(new_pan, new_tilt, verbosity=Verbosity.SILENT)


@api_call(default_verbosity=Verbosity.ACK)
def home() -> Tuple[float, float]:
    """
    Return the pan/tilt head to its centered home position (0°, 0°).

    Returns:
        (0.0, 0.0)

    Note to self:
        Good practice to call this when done with a directed gaze task,
        or as a starting point before a search pattern.
    """
    return move(0.0, 0.0, verbosity=Verbosity.SILENT)


def get_angles() -> Tuple[float, float]:
    """
    Read the current pan/tilt position in degrees.

    Returns:
        (pan_deg, tilt_deg) based on the latest feedback from the Arduino.
        If no feedback has been received yet, returns (0.0, 0.0) which
        is the assumed home position.

    Note to self:
        This reads from a background subscriber that tracks the Arduino's
        reported servo positions. It does NOT command any movement.
        The values may lag slightly behind a recent `move()` command.
    """
    _ensure_subscribers()
    with _position_lock:
        pan = _counts_to_deg_pan(_current_pan_counts, _HOME_PAN_COUNTS)
        tilt = _counts_to_deg_tilt(_current_tilt_counts, _HOME_TILT_COUNTS)
    return (pan, tilt)


