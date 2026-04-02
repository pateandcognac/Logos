# Logos/src/logos/pantilt.py

"""
Control for the pan/tilt mechanism that orients my camera gaze and laser pointer.

The pan/tilt mechanism is my directed gaze — it carries my high-res webcam,
illuminator LEDs, and laser pointer. This module translates between intuitive
degree-space commands and the raw servo protocol spoken by the Arduino.

Coordinate convention (from my perspective, facing forward):
    Pan:  positive = right,  negative = left
    Tilt: positive = up,     negative = down
    Home: (0, 0) = straight ahead, level

Physical limits:
    Pan:  -80° (left)  to +100° (right)
    Tilt: -60° (down)  to  +70° (up)
"""

import time
import threading
import rospy
from std_msgs.msg import Int32
from .core import api_call, Verbosity, check_for_interrupt
from typing import Dict, Optional, Tuple


__all__ = [
    "move", "nudge", "home", "get_position", "look_at_pixel", "look_at_coord",
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
_HOME_TILT_COUNTS = 425

# Physical servo limits for the tilt axis (narrower than full range)
_TILT_SERVO_MIN = 225
_TILT_SERVO_MAX = 550

# ─── Public Constants ────────────────────────────────────────────────

# Degree limits derived from servo limits:
#   deg = (home_counts - servo_counts) / counts_per_deg
PAN_RANGE = (-80.0, 100.0)    # (left_limit, right_limit)
TILT_RANGE = (-60.0, 70.0)    # (down_limit, up_limit)
HOME = (0.0, 0.0)

# Camera FOV in degrees (horizontal, vertical) — used by look_at_pixel.
# Defined per source camera. Astra included for future cross-camera gaze.
FOV: Dict[str, Tuple[float, float]] = {
    "pan_tilt":    (65.0, 50.0),
    "top_down":    (65.0, 50.0),
    "astra_rgb":   (63.0, 49.0),
    "astra_depth": (58.0, 45.0),
}


# ─── Internal Conversion ─────────────────────────────────────────────

def _deg_to_counts(deg: float, home_counts: int) -> int:
    """
    Convert a degree value to servo counts.

    Mapping: servo_counts = home_counts - (deg * counts_per_deg)
    The subtraction inverts direction so that positive degrees map to the
    conventional rightward / upward direction.
    """
    return int(round(home_counts - deg * _COUNTS_PER_DEG))


def _counts_to_deg(counts: int, home_counts: int) -> float:
    """Convert servo counts back to degrees."""
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
    duration: float = 0.5, 
    steps: int = 10
) -> Tuple[float, float]:
    """
    Move the pan/tilt head to an absolute position with interpolation and easing.

    Args:
        pan_deg: Target pan.
        tilt_deg: Target tilt.
        duration: Total time for the movement in seconds.
        steps: Number of intermediate points. Set to 0 or 1 for immediate jumps.

    Returns:
        The clamped (pan, tilt) degrees actually commanded.

    Note to self:
        Interpolation solves the problem of the small servos sometimes getting stuck,
        makes my movements look more natural, and prevents hardware-straining 'snaps',
        and reduces camera shake by easing in quadratically.
    """
    _ensure_subscribers()
    target_pan, target_tilt = _clamp_deg(pan_deg, tilt_deg)
    
    # Get our current starting point
    start_pan, start_tilt = get_position()
    
    # Calculate deltas
    d_pan = target_pan - start_pan
    d_tilt = target_tilt - start_tilt

    # Immediate jump if no duration/steps requested
    if duration <= 0 or steps <= 1:
        p_cnt = _deg_to_counts(target_pan, _HOME_PAN_COUNTS)
        t_cnt = _deg_to_counts(target_tilt, _HOME_TILT_COUNTS)
        _publish_servo(p_cnt, t_cnt, repeat=3)
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
        
        p_cnt = _deg_to_counts(curr_pan, _HOME_PAN_COUNTS)
        t_cnt = _deg_to_counts(curr_tilt, _HOME_TILT_COUNTS)
        
        # Publish current step (no repeat needed during interpolation)
        _publish_servo(p_cnt, t_cnt, repeat=1)
        
        time.sleep(step_delay)

    # Final "Insurance" publish to ensure we are exactly at the target
    final_p = _deg_to_counts(target_pan, _HOME_PAN_COUNTS)
    final_t = _deg_to_counts(target_tilt, _HOME_TILT_COUNTS)
    _publish_servo(final_p, final_t, repeat=3)
    
    return (target_pan, target_tilt)


@api_call(default_verbosity=Verbosity.BRIEF)
def nudge(d_pan: float, d_tilt: float) -> Tuple[float, float]:
    """
    Adjust the pan/tilt head by a relative offset from its current position.

    Args:
        d_pan:  Degrees to add to current pan. Positive = rightward.
        d_tilt: Degrees to add to current tilt. Positive = upward.

    Returns:
        The new absolute (pan, tilt) position in degrees after clamping.

    Note to self:
        Handy for small corrections without needing to know absolute position.
            logos.pantilt.nudge(5, 0)    # Glance a bit more to the right
            logos.pantilt.nudge(0, -10)  # Tilt down a touch
    """
    current_pan, current_tilt = get_position()
    new_pan = current_pan + d_pan
    new_tilt = current_tilt + d_tilt
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


def get_position() -> Tuple[float, float]:
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
        pan = _counts_to_deg(_current_pan_counts, _HOME_PAN_COUNTS)
        tilt = _counts_to_deg(_current_tilt_counts, _HOME_TILT_COUNTS)
    return (pan, tilt)


@api_call(default_verbosity=Verbosity.BRIEF)
def look_at_pixel(
    point_2d: Tuple[float, float],
    source: str = "pan_tilt",
) -> Tuple[float, float]:
    """
    Shift gaze to center a detected point in the image.

    Given a point detected in a camera image (using my normalized 0-1000
    coordinate system), this computes the angular offset from image center
    and adjusts the pan/tilt servos to bring that point to center frame.

    Args:
        point_2d: Detection point as [y, x], each in 0-1000 normalized
            coordinates (y: top=0, bottom=1000; x: left=0, right=1000).
            This matches my native detection format.
        source: Which camera the detection came from. Currently only
            'pan_tilt' is supported (the camera on the pan/tilt head).

    Returns:
        The new absolute (pan, tilt) position in degrees after the move.

    Note to self:
        This is the bridge between my visual perception and physical gaze.
        When I detect something interesting in my pan_tilt image, I can
        immediately look at it:

            detections = [{"point": [300, 700], "label": "interesting_thing"}]
            logos.pantilt.look_at_pixel(detections[0]["point"])

        For objects detected in the astra or top_down cameras, I would need
        to use a different approach (e.g., project through depth to 3D, then
        compute gaze angles), which is not yet implemented.

        The pan_tilt camera image is flipped at capture time to correct for
        its inverted mounting, so pixel coordinates are in natural orientation:
        right-in-image = right-in-world.
    """
    if source != "pan_tilt":
        raise NotImplementedError(
            f"look_at_pixel currently only supports source='pan_tilt'. "
            f"Got '{source}'. Cross-camera gaze requires 3D projection."
        )

    y_norm, x_norm = point_2d

    # Convert from 0-1000 to fraction-from-center (-0.5 to +0.5)
    x_frac = (x_norm / 1000.0) - 0.5  # positive = right of center
    y_frac = (y_norm / 1000.0) - 0.5  # positive = below center

    fov_h, fov_v = FOV[source]

    # Angular offset: how far from image center in degrees
    # Pan:  object right in image → pan right (positive)
    # Tilt: object above in image (negative y_frac) → tilt up (positive)
    pan_offset = x_frac * fov_h
    tilt_offset = -y_frac * fov_v

    current_pan, current_tilt = get_position()
    new_pan = current_pan + pan_offset
    new_tilt = current_tilt + tilt_offset

    return move(new_pan, new_tilt, duration=0.4, verbosity=Verbosity.SILENT)

'''
@api_call(default_verbosity=Verbosity.BRIEF)
def look_at_coord(x: float, y: float, z: float) -> Tuple[float, float]:
    """
    Rotate the pan/tilt head to look at a specific 3D coordinate in the map frame.

    Args:
        x, y, z: The target 3D coordinate in the map frame (meters).
                 Often obtained from `logos.map3d.raycast()`.

    Returns:
        The new absolute (pan, tilt) position in degrees.

    Note to self:
        This is incredibly powerful! I can click on a point in my mind palace
        (map3d render), raycast it to a 3D point, and then physically look at it.
    """
    from . import ros
    
    # We need to transform the target point into the frame of the pan_tilt_link
    # to figure out the angles. We add a small offset because the camera itself
    # is mounted slightly above the servo axis, but aiming from the link is usually
    # close enough for jazz.
    target_frame = "pan_tilt_link"
    # TODO: create a pan-tilt link!?
     
    local_pt = ros.transform_map_to_frame(x, y, z, target_frame)
    if local_pt is None:
        print(f"pantilt: Could not transform target ({x}, {y}, {z}) to {target_frame}.")
        return get_position()
        
    local_x, local_y, local_z = local_pt
    
    # Calculate spherical coordinates (yaw/pitch) from the Cartesian point.
    # In ROS standard frames: X is forward, Y is left, Z is up.
    
    # Yaw (pan) = atan2(y, x). 
    # ROS Y is left (+), but our Pan is right (+). So we negate Y.
    pan_rad = math.atan2(-local_y, local_x)
    
    # Pitch (tilt) = atan2(z, x)
    # Note: math.hypot(x, y) gives the ground distance. 
    # Tilt is the angle 'up' from the horizon.
    dist_xy = math.hypot(local_x, local_y)
    tilt_rad = math.atan2(local_z, dist_xy)
    
    pan_deg = math.degrees(pan_rad)
    tilt_deg = math.degrees(tilt_rad)
    
    return move(pan_deg, tilt_deg, duration=1.0, verbosity=Verbosity.SILENT)
'''