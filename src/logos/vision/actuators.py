# Logos/src/logos/vision/actuators.py

"""
I use this module to control my physical actuators: the pan/tilt mechanism,
the laser pointer, and my various LED arrays.
"""

import rospy
import time
from std_msgs.msg import Int32, UInt8, Int32MultiArray
from .core import (
    PAN_SERVO_MIN, PAN_SERVO_MAX, PAN_SERVO_HOME,
    TILT_SERVO_MIN, TILT_SERVO_MAX, TILT_SERVO_HOME,
    SERVO_DEG_CONVERSION, PAN_DEG_MIN, PAN_DEG_MAX,
    TILT_DEG_MIN, TILT_DEG_MAX
)
from ..core import api_call, Verbosity

# Topics
TOPIC_PAN = '/pan_tilt/move/pan'
TOPIC_TILT = '/pan_tilt/move/tilt'
TOPIC_LASER = '/pan_tilt/laser'
TOPIC_LED_PT = '/pan_tilt/rgbled'
TOPIC_LED_FACE = '/face/rgbled'
TOPIC_LED_HEART = '/notification/rgbled'

class ActuatorController:
    """
    Singleton class to manage ROS publishers for my body.
    """
    def __init__(self):
        # Servos
        self.pub_pan = rospy.Publisher(TOPIC_PAN, Int32, queue_size=5)
        self.pub_tilt = rospy.Publisher(TOPIC_TILT, Int32, queue_size=5)
        
        # Lights & Laser
        self.pub_laser = rospy.Publisher(TOPIC_LASER, UInt8, queue_size=5)
        self.pub_led_pt = rospy.Publisher(TOPIC_LED_PT, Int32MultiArray, queue_size=5)
        self.pub_led_face = rospy.Publisher(TOPIC_LED_FACE, Int32MultiArray, queue_size=5)
        self.pub_led_heart = rospy.Publisher(TOPIC_LED_HEART, Int32MultiArray, queue_size=5)

        # State tracking (Software cache of physical state)
        self.current_pan_servo = PAN_SERVO_HOME
        self.current_tilt_servo = TILT_SERVO_HOME
        self.laser_state = 0 # 0-255

    def _deg_to_servo(self, pan_deg: int, tilt_deg: int) -> tuple:
        """
        Converts degrees to servo values using the legacy flipped mapping.
        Formula: servo = home - (deg * conversion)
        """
        # Clamp inputs
        pan_deg = max(PAN_DEG_MIN, min(PAN_DEG_MAX, pan_deg))
        tilt_deg = max(TILT_DEG_MIN, min(TILT_DEG_MAX, tilt_deg))

        p_servo = int(round(PAN_SERVO_HOME - (pan_deg * SERVO_DEG_CONVERSION)))
        t_servo = int(round(TILT_SERVO_HOME - (tilt_deg * SERVO_DEG_CONVERSION)))
        
        return p_servo, t_servo

    def move_raw(self, pan_raw: int, tilt_raw: int):
        """Sends raw integer values to the servos."""
        # Safety Clamping
        pan_raw = max(PAN_SERVO_MIN, min(PAN_SERVO_MAX, pan_raw))
        tilt_raw = max(TILT_SERVO_MIN, min(TILT_SERVO_MAX, tilt_raw))

        self.current_pan_servo = pan_raw
        self.current_tilt_servo = tilt_raw

        # Legacy redundancy: Publishing multiple times ensures the Arduino catches it
        # (UDP-like behavior over serial bridges sometimes drops packets)
        for _ in range(2):
            self.pub_pan.publish(pan_raw)
            rospy.sleep(0.02)
            self.pub_tilt.publish(tilt_raw)
            rospy.sleep(0.02)

    def set_led_strip(self, topic_pub: rospy.Publisher, colors: list):
        """
        Helper to format and publish LED commands.
        Args:
            topic_pub: The ROS publisher to use.
            colors: A list of tuples/ints. 
                    If tuple: (index, r, g, b) or (index, hex_int)
                    If setting whole strip, can be list of hex ints.
        """
        msg = Int32MultiArray()
        data = []
        
        for item in colors:
            idx = 0
            color_val = 0
            
            if isinstance(item, tuple):
                if len(item) == 4: # (index, r, g, b)
                    idx, r, g, b = item
                    color_val = (r << 16) | (g << 8) | b
                elif len(item) == 2: # (index, hex)
                    idx, color_val = item
            
            # Pack: Left 8 bits = Index, Right 24 bits = Color
            # Ensure index is 0-255
            packed = (idx << 24) | (color_val & 0xFFFFFF)
            data.append(packed)
            
        msg.data = data
        topic_pub.publish(msg)

# Initialize the singleton instance
_actuators = ActuatorController()


# --- Public API Functions ---

@api_call(default_verbosity=Verbosity.BRIEF)
def look_at(pan_degrees: int, tilt_degrees: int):
    """
    Moves my head to the specified angles.
    
    Args:
        pan_degrees: Left (-80) to Right (+100). 0 is center.
        tilt_degrees: Down (-60) to Up (+70). 0 is center.
    """
    p_servo, t_servo = _actuators._deg_to_servo(pan_degrees, tilt_degrees)
    _actuators.move_raw(p_servo, t_servo)

@api_call(default_verbosity=Verbosity.ACK)
def look_home():
    """Resets my head to the center (0, 0) position."""
    _actuators.move_raw(PAN_SERVO_HOME, TILT_SERVO_HOME)

@api_call(default_verbosity=Verbosity.ACK)
def laser(brightness: int = 255):
    """
    Controls my laser pointer.
    
    Args:
        brightness: 0 (Off) to 255 (Max).
    """
    brightness = max(0, min(255, brightness))
    _actuators.laser_state = brightness
    _actuators.pub_laser.publish(brightness)

@api_call(default_verbosity=Verbosity.ACK)
def set_face_leds(led_data: list):
    """
    Controls the RGB LEDs on my face (VU meter strip).
    
    Args:
        led_data: List of (index, r, g, b) tuples. 
                  Index 0-11.
    """
    _actuators.set_led_strip(_actuators.pub_led_face, led_data)

@api_call(default_verbosity=Verbosity.ACK)
def set_heart_light(r: int, g: int, b: int):
    """
    Sets my 'Heart Light' (notification ring).
    Since it's a diffuse ring, we usually set all 16 LEDs to the same color.
    """
    # Create data for all 16 LEDs
    data = [(i, r, g, b) for i in range(16)]
    _actuators.set_led_strip(_actuators.pub_led_heart, data)

@api_call(default_verbosity=Verbosity.ACK)
def set_flash(on: bool = True):
    """
    Controls the high-brightness illuminator on my pan/tilt head.
    """
    color = 0xFFFFFF if on else 0x000000
    # 5 LEDs in the strip
    data = [(i, color) for i in range(5)]
    _actuators.set_led_strip(_actuators.pub_led_pt, data)