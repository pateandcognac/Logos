# src/logos/leds.py

"""
Control for my RGB LED strips and laser pointer.

I have three addressable RGB LED strips and a dimmable laser, all driven
by Arduinos that listen on ROS topics. This module provides a clean
interface over the raw Int32MultiArray / UInt8 protocol.

Hardware layout:
    - 'notification':  16 LEDs on /notification/rgbled
    - 'pan_tilt':       5 LEDs on /pan_tilt/rgbled
    - laser:           PWM 0-255 on /pan_tilt/laser
"""

import rospy
from std_msgs.msg import Int32MultiArray, UInt8
from .core import api_call, Verbosity
from typing import Dict, List, Optional, Sequence, Tuple, Union
import time

__all__ = ["set", "fill", "off", "laser", "STRIPS"]


# ─── Strip Configuration ─────────────────────────────────────────────

STRIPS: Dict[str, dict] = {
    "notification": {"topic": "/notification/rgbled",  "count": 16},
    "pan_tilt":     {"topic": "/pan_tilt/rgbled",      "count": 5},
    # "face":         {"topic": "/face/rgbled",         "count": 12},
}

_LASER_TOPIC = "/pan_tilt/laser"

# Named color palette for convenience
_NAMED_COLORS: Dict[str, int] = {
    "off":     0x000000,
    "white":   0xFFFFFF,
    "red":     0xFF0000,
    "green":   0x00FF00,
    "blue":    0x0000FF,
    "yellow":  0xFFFF00,
    "cyan":    0x00FFFF,
    "magenta": 0xFF00FF,
    "orange":  0xFF8000,
    "purple":  0x8000FF,
    "warm":    0xFFB060,
    "indigo":  0x560591,
    "lime":    0xBFFF00,
    "gold":    0xAAAA00,
}


# ─── Lazy Publishers ──────────────────────────────────────────────────

_publishers: Dict[str, rospy.Publisher] = {}
_laser_pub: Optional[rospy.Publisher] = None


def _get_strip_pub(strip: str) -> rospy.Publisher:
    """Get or create the publisher for a given strip."""
    if strip not in STRIPS:
        raise ValueError(
            f"Unknown strip '{strip}'. Choose from: {list(STRIPS.keys())}"
        )
    if strip not in _publishers:
        topic = STRIPS[strip]["topic"]
        _publishers[strip] = rospy.Publisher(
            topic, Int32MultiArray, queue_size=10
        )
    return _publishers[strip]


def _get_laser_pub() -> rospy.Publisher:
    """Get or create the laser publisher."""
    global _laser_pub
    if _laser_pub is None:
        _laser_pub = rospy.Publisher(_LASER_TOPIC, UInt8, queue_size=10)
    return _laser_pub


# ─── Color Normalization ─────────────────────────────────────────────

# Color type: hex int, RGB tuple, or named string
ColorValue = Union[int, Tuple[int, int, int], str]


def _normalize_color(color: ColorValue) -> int:
    """
    Convert a color value to a 24-bit 0xRRGGBB integer.

    Accepts:
        - int:   0xFF0000 (red), 0x000000 (off)
        - tuple: (255, 0, 0) for red
        - str:   'red', 'off', 'white', etc. from the named palette.
                 Also accepts '#FF0000' hex strings.
    """
    if isinstance(color, int):
        return color & 0xFFFFFF

    if isinstance(color, (tuple, list)):
        if len(color) != 3:
            raise ValueError(f"RGB tuple must have 3 elements, got {len(color)}")
        r, g, b = [max(0, min(255, int(c))) for c in color]
        return (r << 16) | (g << 8) | b

    if isinstance(color, str):
        # Check named palette first
        lower = color.lower().strip()
        if lower in _NAMED_COLORS:
            return _NAMED_COLORS[lower]
        # Try hex string like '#FF0000' or 'FF0000'
        hex_str = lower.lstrip("#")
        if len(hex_str) == 6:
            try:
                return int(hex_str, 16)
            except ValueError:
                pass
        raise ValueError(
            f"Unknown color '{color}'. Named options: {list(_NAMED_COLORS.keys())}"
        )

    raise TypeError(f"Unsupported color type: {type(color)}")


def _pack_led(index: int, color_int: int) -> int:
    """Pack an LED index and 24-bit color into the Arduino's Int32 protocol."""
    return (index << 24) | (color_int & 0xFFFFFF)


# ─── Public API ────

@api_call(default_verbosity=Verbosity.ACK)
def set(
    strip: Optional[str] = "notification",
    colors: Sequence[ColorValue] = (),
) -> None:
    """
    Set individual LED colors on a strip ('notification' or 'pan_tilt').

    Args:
        strip: Which strip to address. Defaults to 'notification'.
        colors: A sequence of color values, one per LED. Length must match
            the strip's LED count, or be shorter (remaining LEDs unchanged).
            Each element can be a hex int, RGB tuple, or named color string.

    Note to self:
        Use this for per-LED patterns, animations, or gradients.
        For solid colors, `fill()` is simpler.

        Example:
            # Set first 3 pan_tilt LEDs to different colors
            logos.leds.set('pan_tilt', ['red', 'green', 'blue'])

            # notification strip with RGB tuples
            logos.leds.set('notification', [(255,0,0)] * 5 + [(0,255,0)] * 5 + [(0,0,255)] * 5)
    """
    strip = strip or "notification"
    pub = _get_strip_pub(strip)
    led_count = STRIPS[strip]["count"]

    if len(colors) > led_count:
        raise ValueError(
            f"Strip '{strip}' has {led_count} LEDs, got {len(colors)} colors"
        )

    msg = Int32MultiArray()
    msg.data = [
        _pack_led(i, _normalize_color(c))
        for i, c in enumerate(colors)
    ]
    for _ in range(5):
        pub.publish(msg)
        time.sleep(0.01)

@api_call(default_verbosity=Verbosity.ACK)
def fill(
    color: ColorValue = "off",
    strip: Optional[str] = "notification",
) -> None:
    """
    Set all LEDs on a strip ('notification' bubble or 'pan_tilt' flash illuminator) to the same color (hex int, RGB tuple, or named string).

    Args:
        color: A single color value (hex int, RGB tuple, or named string).
            When passed as the only positional argument, it targets the
            default 'notification' strip.
        strip: Which strip to address. Defaults to 'notification'.

    Note to self:
        Quick way to light up or blank a strip.

        Example:
            logos.leds.fill('cyan')
            logos.leds.fill((0, 100, 255))
            logos.leds.fill('pan_tilt', 0xFFFFFF)  # Backward-compatible old order
            logos.leds.fill(0xFFFFFF, 'pan_tilt')  # Preferred explicit order
    """
    # Backward compatibility for the previous API shape:
    # fill('pan_tilt', 'blue') -> fill('blue', 'pan_tilt')
    if isinstance(color, str) and color in STRIPS and strip not in STRIPS:
        color, strip = strip, color

    strip = strip or "notification"
    led_count = STRIPS[strip]["count"]
    color_int = _normalize_color(color)
    set(strip, [color_int] * led_count, verbosity=Verbosity.SILENT)


@api_call(default_verbosity=Verbosity.ACK)
def off(strip: Optional[str] = None) -> None:
    """
    Turn off LEDs. If strip is None, turns off ALL strips and the laser.

    Args:
        strip: Specific strip to turn off, or None for everything.

    Note to self:
        Good hygiene to call `logos.leds.off()` at the end of a light show
        or when entering idle state.
    """
    targets = [strip] if strip else list(STRIPS.keys())
    for s in targets:
        fill("off", s, verbosity=Verbosity.SILENT)
    if strip is None:
        laser(0.0, verbosity=Verbosity.SILENT)


@api_call(default_verbosity=Verbosity.ACK)
def laser(brightness: float) -> None:
    """
    Set the laser pointer brightness 0.0 to 1.0

    Args:
        brightness: Float from 0.0 (off) to 1.0 (full power).
            Values are clamped to this range.

    Note to self:
        The laser is mounted on the pan/tilt head, so it points wherever
        my pan_tilt camera is looking. Useful for pointing at things in
        the environment to draw human attention, or for cat enrichment.

        Example:
            logos.leds.laser(1.0)   # Full power
            logos.leds.laser(0.5)   # Half brightness
            logos.leds.laser(0.0)   # Off
    """
    clamped = max(0.0, min(1.0, brightness))
    pwm_value = int(round(clamped * 255))
    pub = _get_laser_pub()
    msg = UInt8()
    msg.data = pwm_value
    for _ in range(5):
        pub.publish(msg)
        time.sleep(0.01)
