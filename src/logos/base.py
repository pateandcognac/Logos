# src/logos/base.py

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
    from nav_msgs.msg import Odometry
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

__all__ = [
    "get_bumpers", "get_cliffs", "get_wheel_drops",
    "get_battery", "get_charger_state", "get_buttons",
    "get_odom",
    "velocity", "move_timed", "stop"
]

# ─── Internal State & Constants ───────────────────────────────────────

_latest_state: Optional['SensorState'] = None
_state_lock = threading.Lock()
_ros_initialized = False

_latest_odom: Optional['Odometry'] = None
_odom_lock = threading.Lock()

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

def _odom_cb(msg):
    """Callback for the /odom topic."""
    global _latest_odom
    with _odom_lock:
        _latest_odom = msg

def _ensure_ros():
    """Lazily initializes the SensorState and odometry subscribers."""
    global _ros_initialized
    if not _HAS_ROS or _ros_initialized:
        return

    rospy.Subscriber(
        "/mobile_base/sensors/core",
        SensorState,
        _sensor_cb,
        queue_size=1,
    )

    rospy.Subscriber(
        "/odom",
        Odometry,
        _odom_cb,
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
        - 'voltage' (float): Current battery voltage (e.g., 15.8).
        - 'percent' (float): Estimated charge percentage (0.0 to 100.0).
        - 'status' (str): Semantic assessment ('healthy', 'low', 'critical').

    Note to self:
        A fully charged Kobuki battery is around 15.8V. It is considered 
        critically low around 13.5V. 
    """
    _ensure_ros()
    retries = 0
    max_retries = 5 # for slow startup issues
    delay_s = 0.01 # Tiny delay of 100 milliseconds
    while retries < max_retries:
        with _state_lock:
            # Check if _latest_state is available now
            if _latest_state is not None:
                voltage = _latest_state.battery * 0.1
                # Simple linear estimation between 13.5V (0%) and 15.8 (100%)
                percent = max(0.0, min(100.0, ((voltage - 13.5) / (15.8 - 13.5)) * 100.0))
                if percent > 35.0: status = "healthy"
                elif percent > 14.0: status = "low"
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

def get_odom() -> Dict[str, float]:
    """
    Read my current odometric pose and velocity from the /odom topic.

    Returns:
        A dictionary:
        - 'x' (float): Position along the odom X axis in metres.
        - 'y' (float): Position along the odom Y axis in metres.
        - 'yaw' (float): Heading in degrees (0 = forward at startup, + = left).
        - 'linear_x' (float): Current forward velocity in m/s.
        - 'angular_z_deg' (float): Current rotational velocity in deg/s.
        All fields are 0.0 if no odometry message has arrived yet.

    Note to self:
        Odometry drifts — treat x/y as a relative displacement reference, not
        an absolute world position. Reset to zero whenever I re-dock or
        whenever nav resets the odom frame. The yaw convention matches the
        `velocity()` angular_z_deg sign: positive turns me left (CCW).
    """
    _ensure_ros()
    with _odom_lock:
        if _latest_odom is None:
            return {'x': 0.0, 'y': 0.0, 'yaw': 0.0, 'linear_x': 0.0, 'angular_z_deg': 0.0}

        pos = _latest_odom.pose.pose.position
        q   = _latest_odom.pose.pose.orientation
        # Yaw from quaternion (rotation around Z axis)
        yaw_rad = math.atan2(
            2.0 * (q.w * q.z + q.x * q.y),
            1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        )
        return {
            'x':             round(pos.x, 4),
            'y':             round(pos.y, 4),
            'yaw':           round(math.degrees(yaw_rad), 2),
            'linear_x':      round(_latest_odom.twist.twist.linear.x, 4),
            'angular_z_deg': round(math.degrees(_latest_odom.twist.twist.angular.z), 2),
        }


# ─── Public Movement API ──────────────────────────────────────────────

@api_call(default_verbosity=Verbosity.SILENT)
def velocity(linear_x: float, angular_z_deg: float, topic: str = "muxed") -> None:
    """
    Publish a single, non-blocking velocity command to the base.

    Args:
        linear_x: Forward/backward speed in m/s.
        angular_z_deg: Rotational speed in deg/s.
        topic: [raw|muxed|safety] Default: 'muxed'

    Note to self:
        This is perfect for control loops (like tracking). The Kobuki hardware 
        has a ~0.6s timeout. If you don't call this again within that window, 
        the base will automatically halt. `muxed` is smoothed and has lower
    """
    global _cmd_vel_pub, _cmd_vel_topic

    _ensure_ros()
    if not _HAS_ROS or not rospy.core.is_initialized():
        return

    topic = topic.lower()
    resolved_topic = _TOPIC_MAP.get(topic, _TOPIC_MAP["raw"])

    if _cmd_vel_pub is None or _cmd_vel_topic != resolved_topic:
        _cmd_vel_pub = rospy.Publisher(resolved_topic, Twist, queue_size=5)
        _cmd_vel_topic = resolved_topic
        rospy.sleep(0.05)

    cmd = Twist()
    cmd.linear.x = linear_x
    cmd.angular.z = math.radians(angular_z_deg)
    _cmd_vel_pub.publish(cmd)


@api_call(default_verbosity=Verbosity.BRIEF)
def move_timed(linear_x: float, angular_z_deg: float, duration: float, topic: str = "raw") -> None:
    """
    Block and move the base at a specific velocity for a set duration.

    Args:
        linear_x: Forward/backward speed in m/s.
        angular_z_deg: Rotational speed in deg/s.
        duration: Time in seconds to hold this velocity.
        topic: [raw|muxed|safety] Default: 'muxed'

    Note to self:
        Use this for scripted, open-loop movements (like wiggles, dances, 
        or backing up blindly). Execution pauses here until the duration ends.
    """
    rate = rospy.Rate(10)
    end_time = time.time() + duration

    while time.time() < end_time:
        check_for_interrupt()
        # We reuse the new single-publish velocity function here!
        velocity(linear_x, angular_z_deg, topic=topic, verbosity=Verbosity.SILENT)
        rate.sleep()

    stop(topic=topic, verbosity=Verbosity.SILENT)

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
    for _ in range(5):
        _cmd_vel_pub.publish(cmd)
        rospy.sleep(0.06)