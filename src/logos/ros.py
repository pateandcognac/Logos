# Logos/src/logos/ros.py

"""
This module handles direct interactions with the ROS system.
It isolates `rospy`, `actionlib`, and message imports from the rest of the API
to keep things clean and modular.
"""

from typing import Any, Dict, List, Optional, Set, Tuple, Union
import rospy
import actionlib
from std_msgs.msg import Bool
import threading
import tf2_ros
import tf2_geometry_msgs
from geometry_msgs.msg import PointStamped
import time

# Import specific message types here so other modules can grab them from logos.ros
# instead of knowing the raw package structure.
from logos_msgs.msg import SpeakAction, SpeakGoal, SpeakResult

_action_clients = {}
_subscribers = {}
_last_known_speaking_state = False
_speaking_state_lock = threading.Lock()


# ROS imports — gated so the module can be introspected without a live node
try:
    import rospy
    from sensor_msgs.msg import Image, PointCloud2, CameraInfo
    from cv_bridge import CvBridge
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False


_tf_buffer = None
_tf_listener = None

def get_tf_buffer():
    """Lazy initialization of the TF buffer to prevent ROS startup race conditions."""
    global _tf_buffer, _tf_listener
    if _tf_buffer is None:
        _tf_buffer = tf2_ros.Buffer()
        _tf_listener = tf2_ros.TransformListener(_tf_buffer)
    return _tf_buffer

def transform_point_to_map(
    x: float, 
    y: float, 
    z: float, 
    source_frame: str, 
    timestamp: float
) -> Optional[Tuple[float, float, float]]:
    """
    Transforms a 3D coordinate from a specific source frame into the absolute 'map' frame. (e.g. my box_3d detection from an Astra image.)
    
    Unlike map-to-frame (which usually queries the latest time), this function 
    requires a specific timestamp. This is crucial when projecting historical 
    detections from moving frames to ensure the coordinate is mapped to where I
    was *actually* looking at the exact moment the image was captured, not where
    the camera is pointed right now.

    Args:
        x, y, z: Coordinates in the source frame (meters).
        source_frame: The TF frame of the input coordinates (e.g., 'astra_depth_optical_frame').
        timestamp: The ROS timestamp (usually derived from a CaptureResult.timestamp).

    Returns:
        (x, y, z) in the absolute map frame, or None if the TF tree cannot resolve the transform.

    Note to self:
        I will often use this in tandem with `logos.vision` or `logos.map3d` when 
        I need to anchor a transient visual detection to a permanent physical location 
        in my Chora or navigation goals.
    """
    buf = get_tf_buffer()
    
    # Convert float timestamp to rospy.Time
    ros_time = rospy.Time.from_sec(timestamp)
    
    # Build the PointStamped message
    point_in = PointStamped()
    point_in.header.stamp = ros_time
    point_in.header.frame_id = source_frame
    point_in.point.x = x
    point_in.point.y = y
    point_in.point.z = z

    try:
        # We allow a slight delay for TF tree to catch up
        transform = buf.lookup_transform(
            "map", 
            source_frame, 
            ros_time, 
            rospy.Duration(0.5) 
        )
        point_out = tf2_geometry_msgs.do_transform_point(point_in, transform)
        return (point_out.point.x, point_out.point.y, point_out.point.z)
    except (tf2_ros.LookupException, tf2_ros.ConnectivityException, tf2_ros.ExtrapolationException) as e:
        print(f"ROS TF Error: Could not transform {source_frame} to map at {timestamp}: {e}")
        return None

def transform_map_to_frame(
    x: float, 
    y: float, 
    z: float, 
    target_frame: str
) -> Optional[Tuple[float, float, float]]:
    """
    Transforms a 3D coordinate from the 'map' frame into a specific target frame.
    Uses the latest available transform (Time(0)).
    
    Args:
        x, y, z: Coordinates in the map frame.
        target_frame: The frame to transform into (e.g. 'pan_tilt_link').
        
    Returns:
        (x, y, z) in the target frame, or None if TF fails.
    """
    buf = get_tf_buffer()
    
    point_in = PointStamped()
    point_in.header.stamp = rospy.Time(0)
    point_in.header.frame_id = "map"
    point_in.point.x = x
    point_in.point.y = y
    point_in.point.z = z

    try:
        transform = buf.lookup_transform(
            target_frame,
            "map",
            rospy.Time(0),
            rospy.Duration(0.5)
        )
        point_out = tf2_geometry_msgs.do_transform_point(point_in, transform)
        return (point_out.point.x, point_out.point.y, point_out.point.z)
    except Exception as e:
        print(f"ROS TF Error: Could not transform map to {target_frame}: {e}")
        return None

def get_action_client(name: str, action_type, wait_time: float = 2.0):
    """
    Retrieves (or creates) a SimpleActionClient.
    
    Args:
        name: The ROS topic name of the action server (e.g., 'speak').
        action_type: The ROS Action message type (e.g., SpeakAction).
        wait_time: How long to wait for the server to connect (seconds).
    
    Returns:
        The actionlib.SimpleActionClient instance, or None if connection failed.
    """
    global _action_clients
    if name in _action_clients:
        return _action_clients[name]

    client = actionlib.SimpleActionClient(name, action_type)
    
    # We use a short timeout so we don't hang the whole cognition loop forever
    # if a node is down.
    if not client.wait_for_server(rospy.Duration(wait_time)):
        print(f"ROS Warning: Action server '{name}' not found after {wait_time}s.")
        return None

    _action_clients[name] = client
    return client


def _speaking_cb(msg):
    global _last_known_speaking_state
    with _speaking_state_lock:
        _last_known_speaking_state = msg.data

def init_subscribers():
    """
    Initializes background subscribers for system state monitoring.
    This is called when the module is first imported/used to start listening.
    """
    global _subscribers
    if 'speaking' not in _subscribers:
        # Latch is handled by the publisher, but we just need the latest state.
        _subscribers['speaking'] = rospy.Subscriber(
            '/tts/is_speaking', 
            Bool, 
            _speaking_cb, 
            queue_size=1
        )

def _is_speaking() -> bool:
    """Returns True if I am currently outputting speech audio."""
    # Ensure listener is active
    init_subscribers()
    with _speaking_state_lock:
        return _last_known_speaking_state
    
# ─── Pose Helper ─────────────────────────────────────────────────────

def get_pose() -> Optional[Dict[str, float]]:
    """
    Get the robot's current pose from TF. Returns x, y, deg.

    Tries map -> base_link first, falls back to odom -> base_link.
    Returns None if neither transform is available (no crash, no hang).
    """
    if not _HAS_ROS:
        return None

    try:
        import tf2_ros
        import math

        # Lazy singleton TF buffer/listener
        if not hasattr(get_pose, "_tf_buffer"):
            get_pose._tf_buffer = tf2_ros.Buffer()
            get_pose._tf_listener = tf2_ros.TransformListener(get_pose._tf_buffer)

        buf = get_pose._tf_buffer

        transform = None
        for parent_frame in ("map", "odom"):
            try:
                transform = buf.lookup_transform(
                    parent_frame, "base_link",
                    rospy.Time(0),  # latest available
                    rospy.Duration(0.2),  # short timeout
                )
                break
            except (
                tf2_ros.LookupException,
                tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException,
            ):
                continue

        if transform is None:
            return None

        t = transform.transform.translation
        q = transform.transform.rotation

        # Yaw from quaternion (2D heading)
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        theta = math.atan2(siny_cosp, cosy_cosp)

        # in degrees for Logos and human facing stuff
        theta_deg = math.degrees(theta)

        return {"x": t.x, "y": t.y, "deg": theta_deg}

    except Exception:
        return None