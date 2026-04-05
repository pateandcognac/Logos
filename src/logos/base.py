# Logos/src/logos/base.py

"""
This module provides access to the Kobuki mobile base. It allows me to read my physical sensors (bumpers, cliffs, battery) and issue raw velocity commands to my wheels.

This is my "lower brain" interface. It bypasses the navigation map entirely.
"""

import time
import threading
from typing import Dict, List, Optional, Tuple, Union
from .core import api_call, Verbosity, check_for_interrupt
import math

# ROS imports gated for offline introspection
try:
    import rospy
    from kobuki_msgs.msg import SensorState
    from geometry_msgs.msg import Twist
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

__all__ = [
    "get_bumpers", "get_cliffs", "get_wheel_drops", 
    "get_battery", "get_charger_state", "get_buttons",
    "velocity", "stop"
]

# ─── Internal State & Constants ───────────────────────────────────────

_latest_state: Optional['SensorState'] = None
_state_lock = threading.Lock()
_ros_initialized = False

_cmd_vel_pub: Optional['rospy.Publisher'] = None
_cmd_vel_topic: Optional[str] = None

_TOPIC_MAP = {
    "raw": "/raw_cmd_vel",
    "muxed": "/cmd_vel_mux/input/logos",
    "safety": "/cmd_vel_mux/input/safety_controller"
}

# Semantic mappings for Kobuki bitmasks
_BUMPER_MAP = {1: 'right', 2: 'center', 4: 'left'}
_WHEEL_DROP_MAP = {1: 'right', 2: 'left'}
_CLIFF_MAP = {1: 'right', 2: 'center', 4: 'left'}
_BUTTON_MAP = {1: 'button0', 2: 'button1', 4: 'button2'}

_CHARGER_MAP = {
    0: 'discharging',
    2: 'docking_charged',
    6: 'docking_charging',
    18: 'adapter_charged',
    22: 'adapter_charging'
}

# ─── ROS Initialization ───────────────────────────────────────────────

def _sensor_cb(msg):
    """Callback for the 50Hz SensorState topic."""
    global _latest_state
    with _state_lock:
        _latest_state = msg

def _ensure_ros():
    """Lazily initializes the SensorState subscriber."""
    global _ros_initialized
    if not _HAS_ROS or _ros_initialized:
        return

    rospy.Subscriber(
        "/mobile_base/sensors/core",
        SensorState,
        _sensor_cb,
        queue_size=1,
    )

    _ros_initialized = True
    time.sleep(0.1)

def _parse_bitmask(value: int, mapping: Dict[int, str]) -> List[str]:
    """Helper to convert a single integer bitmask into a list of semantic strings."""
    return [name for bit, name in mapping.items() if (value & bit)]

# ─── Public Sensor API ────────────────────────────────────────────────

def get_bumpers() -> List[str]:
    """
    Check if my physical bumpers are currently pressed against an obstacle.

    Returns:
        A list of strings indicating pressed bumpers: 'left', 'center', 'right'.
        Returns an empty list [] if no bumpers are pressed.

    Note to self:
        This is a live read of my tactile sensors. Useful for close-quarters 
        maneuvering or verifying if I'm physically blocked.
    """
    _ensure_ros()
    with _state_lock:
        if _latest_state is None: return []
        return _parse_bitmask(_latest_state.bumper, _BUMPER_MAP)

def get_cliffs() -> List[str]:
    """
    Check my downward-facing cliff sensors (stairs, ledges, drop-offs).

    Returns:
        A list of strings indicating triggered cliff sensors: 'left', 'center', 'right'.
        Returns an empty list [] if solid ground is detected under all sensors.

    Note to self:
        If this returns anything, I am in imminent danger of falling. 
        My autonomic safety controller usually stops me automatically, but I 
        can read this to understand *why* I stopped.
    """
    _ensure_ros()
    with _state_lock:
        if _latest_state is None: return []
        return _parse_bitmask(_latest_state.cliff, _CLIFF_MAP)

def get_wheel_drops() -> List[str]:
    """
    Check if my drive wheels have dropped, meaning I have been lifted, tipped, or am on a precipice.

    Returns:
        A list of strings indicating dropped wheels: 'left', 'right'.
        Returns an empty list [] if my wheels are carrying weight.

    Note to self:
        If this triggers, I have likely been picked up by a human, wobbled
        over a threshold, or am partially hanging off a cliff!
    """
    _ensure_ros()
    with _state_lock:
        if _latest_state is None: return []
        return _parse_bitmask(_latest_state.wheel_drop, _WHEEL_DROP_MAP)

def get_battery() -> Dict[str, Union[float, str]]:
    """
    Read my current battery `percent`, `voltage`, and semantic `status`.

    Returns:
        A dictionary:
        - 'voltage' (float): Current battery voltage (e.g., 16.2).
        - 'percent' (float): Estimated charge percentage (0.0 to 100.0).
        - 'status' (str): Semantic assessment ('healthy', 'low', 'critical').

    Note to self:
        A fully charged Kobuki battery is around 16.5V. It is considered 
        critically low around 13.5V. 
    """
    _ensure_ros()
    retries = 0
    max_retries = 10 # for slow startup issues
    delay_s = 0.1 # Tiny delay of 100 milliseconds
    while retries < max_retries:
        with _state_lock:
            # Check if _latest_state is available now
            if _latest_state is not None:
                voltage = _latest_state.battery * 0.1
                # Simple linear estimation between 13.5V (0%) and 16.2 (100%)
                percent = max(0.0, min(100.0, ((voltage - 13.5) / (16.2 - 13.5)) * 100.0))
                if percent > 30.0: status = "healthy"
                elif percent > 15.0: status = "low"
                else: status = "critical"
                return {'voltage': round(voltage, 2), 'percent': round(percent, 1), 'status': status}
            else:
                # _latest_state is None, increment retry counter and wait
                retries += 1
                time.sleep(delay_s)
    # If we exhaust retries and _latest_state is still None, return unknown
    return {'voltage': 0.0, 'percent': 0.0, 'status': 'unknown'}

def get_charger_state() -> str:
    """
    Check if I am currently connected to power.

    Returns:
        A string representing my charging state: 'discharging', 'docking_charged',
        'docking_charging', 'adapter_charged', or 'adapter_charging'.

    Note to self:
        If this says 'discharging', I am running on battery power. 
        If I am on my dock, it will say 'docking_charging' or 'docking_charged'.
    """
    _ensure_ros()
    with _state_lock:
        if _latest_state is None: return 'unknown'
        return _CHARGER_MAP.get(_latest_state.charger, 'unknown')

def get_buttons() -> List[str]:
    """
    Check if any physical buttons on my torso are being pressed.

    Returns:
        A list of strings: 'button0', 'button1', 'button2'.
        Returns an empty list [] if no buttons are pressed.
    """
    _ensure_ros()
    with _state_lock:
        if _latest_state is None: return []
        return _parse_bitmask(_latest_state.buttons, _BUTTON_MAP)


# ─── Public Movement API ──────────────────────────────────────────────

@api_call(default_verbosity=Verbosity.BRIEF)
def velocity(
    linear_x: float,
    angular_z_deg: float,
    duration: float,
    topic: str = "raw",
) -> None:
    """
    Send raw velocity commands to a 'raw' (default) velocity topic or 'muxed' and *smoothed* topic for a specific duration.

    Args:
        linear_x: Forward/backward speed in meters per second (m/s). 
                  Positive is forward, negative is backward. (Max ~0.70)
        angular_z_deg: Rotational speed in degrees per second (deg/s). 
                   Positive is counter-clockwise (left), negative is clockwise (right). (Max ~110)
        duration: How long to apply this velocity, in seconds.
        topic:    [raw|muxed] Default: *raw*

    Note to self:
        This is for raw, map-ignorant movement! I use 'raw' for short, sharp 
        movements where I want to overcome inertia quickly (e.g., wiggles, 
        dances). I can use 'muxed' for smoother, "teleop-style" movements
        that respect the standard acceleration limits.

        The safety controller can still override me if I am about to hit a wall.
        This function blocks execution until the duration is complete, publishing 
        the velocity at 10Hz to the Kobuki motor timeout watchdog.

        Example:
            logos.base.velocity(0.2, 0.0, 2.0)   # Move forward 0.2 m/s for 2 seconds
            logos.base.velocity(0.0, 5.0, 3.0)   # Spin left 5 deg/s for 3 seconds
    """
    global _cmd_vel_pub, _cmd_vel_topic

    _ensure_ros()
    if not _HAS_ROS:
        print("base: Cannot move, ROS not available.")
        return

    # Optional but helpful: fail loudly if nobody called rospy.init_node()
    if not rospy.core.is_initialized():
        print("base: Cannot move, rospy.init_node() has not been called.")
        return

    topic = topic.lower()
    if topic not in _TOPIC_MAP:
        raise ValueError(
            f"Invalid topic alias '{topic}'. Valid options: {list(_TOPIC_MAP.keys())}"
        )

    resolved_topic = _TOPIC_MAP[topic]

    # Create/recreate publisher if needed
    if _cmd_vel_pub is None or _cmd_vel_topic != resolved_topic:
        _cmd_vel_pub = rospy.Publisher(resolved_topic, Twist, queue_size=5)
        _cmd_vel_topic = resolved_topic
        rospy.sleep(0.05)

    # ---- everything below here can stay the same as your current code ----
    cmd = Twist()
    cmd.linear.x = linear_x
    cmd.angular.z = math.radians(angular_z_deg)

    rate = rospy.Rate(10)
    end_time = time.time() + duration

    while time.time() < end_time:
        check_for_interrupt()
        _cmd_vel_pub.publish(cmd)
        rate.sleep()

    stop(verbosity=Verbosity.SILENT)

@api_call(default_verbosity=Verbosity.ACK)
def stop(topic: str = "raw") -> None:
    """
    Immediately halt all base movement by publishing zero velocities.
    """
    global _cmd_vel_pub, _cmd_vel_topic

    _ensure_ros()
    if not _HAS_ROS:
        return

    # If we've already published before, stop on that same topic by default.
    resolved_topic: str
    if _cmd_vel_pub is not None and _cmd_vel_topic is not None:
        resolved_topic = _cmd_vel_topic
    else:
        topic = topic.lower()
        if topic not in _TOPIC_MAP:
            raise ValueError(
                f"Invalid topic alias '{topic}'. Valid options: {list(_TOPIC_MAP.keys())}"
            )
        resolved_topic = _TOPIC_MAP[topic]

    # Ensure publisher exists for the chosen stop topic
    if _cmd_vel_pub is None or _cmd_vel_topic != resolved_topic:
        _cmd_vel_pub = rospy.Publisher(resolved_topic, Twist, queue_size=5)
        _cmd_vel_topic = resolved_topic
        rospy.sleep(0.05)

    cmd = Twist()  # all zeros
    _cmd_vel_pub.publish(cmd)