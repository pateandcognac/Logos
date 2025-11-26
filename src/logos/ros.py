# Logos/src/logos/ros.py

"""
This module handles direct interactions with the ROS system.
It isolates `rospy`, `actionlib`, and message imports from the rest of the API
to keep things clean and modular.
"""

import rospy
import actionlib
from std_msgs.msg import Bool
import threading

# Import specific message types here so other modules can grab them from logos.ros
# instead of knowing the raw package structure.
from logos_msgs.msg import SpeakAction, SpeakGoal, SpeakResult

_action_clients = {}
_subscribers = {}
_last_known_speaking_state = False
_speaking_state_lock = threading.Lock()

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

def is_speaking() -> bool:
    """Returns True if I am currently outputting speech audio."""
    # Ensure listener is active
    init_subscribers()
    with _speaking_state_lock:
        return _last_known_speaking_state