# src/logos/bumper.py

"""
My event-driven bumper collision system.

I transform the raw 50 Hz SensorState stream from my Kobuki base into an
ordered, composable callback chain that fires only on rising edges — the
moment of initial contact, not while the bumper remains pressed.

Handlers in the chain are called sequentially in a background daemon thread,
so they can safely use blocking operations like base.move_timed() or
emote.ttp() without ever stalling the 50 Hz ROS subscriber that feeds them.

While a handler chain is running, new bump events are debounced (dropped)
to prevent pile-up during slow operations like gaze + vision + speech.

Typical usage::

    logos.bumper.set_default()                         # print + back up
    logos.bumper.register(logos.bumper.look_and_identify)
    logos.bumper.show()

    # Swap to a minimal chain for a navigation run
    logos.bumper.clear()
    logos.bumper.register(logos.bumper.do_stop)
"""

import threading
from typing import Callable, List, Optional

try:
    import rospy
    from kobuki_msgs.msg import SensorState as _SensorState
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

from logos.core import api_call, Verbosity


# ---------------------------------------------------------------------------
# Bumper bitmask — mirrors base.py, kept local to avoid private imports.
# ---------------------------------------------------------------------------

_BUMPER_MAP = {1: 'right', 2: 'center', 4: 'left'}


# ---------------------------------------------------------------------------
# Internal state
# ---------------------------------------------------------------------------

_handlers: List[Callable[[List[str]], None]] = []
_handlers_lock = threading.Lock()

_prev_bumper_byte: int = 0      # last raw bitmask seen from the sensor
_prev_lock = threading.Lock()   # guards _prev_bumper_byte

_handling = threading.Event()   # set while a handler chain is executing
_subscriber = None
_subscriber_lock = threading.Lock()


# ---------------------------------------------------------------------------
# ROS internals
# ---------------------------------------------------------------------------

def _parse_bumper_byte(value: int) -> List[str]:
    return [name for bit, name in _BUMPER_MAP.items() if value & bit]


def _sensor_cb(msg) -> None:
    """50 Hz SensorState callback. I detect rising edges and dispatch handlers."""
    global _prev_bumper_byte
    with _prev_lock:
        rising = msg.bumper & ~_prev_bumper_byte
        _prev_bumper_byte = msg.bumper

    if not rising or _handling.is_set():
        return

    bumpers = _parse_bumper_byte(rising)
    _handling.set()
    threading.Thread(target=_run_handlers, args=(bumpers,), daemon=True).start()


def _run_handlers(bumpers: List[str]) -> None:
    """Execute the handler chain in a background thread, then clear the debounce flag."""
    try:
        with _handlers_lock:
            chain = list(_handlers)
        for h in chain:
            try:
                h(bumpers)
            except Exception as e:
                print("[bumper] handler {!r} error: {}".format(
                    getattr(h, '__name__', h), e))
    finally:
        _handling.clear()


def _ensure_subscriber() -> None:
    global _subscriber
    if not _HAS_ROS:
        return
    with _subscriber_lock:
        if _subscriber is not None:
            return
        _subscriber = rospy.Subscriber(
            '/mobile_base/sensors/core',
            _SensorState,
            _sensor_cb,
            queue_size=1,
        )


# ---------------------------------------------------------------------------
# Public handler management
# ---------------------------------------------------------------------------

@api_call(default_verbosity=Verbosity.ACK)
def register(handler: Callable[[List[str]], None], index: Optional[int] = None) -> None:
    """Add a handler to my bumper event chain.

    I append the handler at the end of the chain by default, or insert it at
    the given index. The chain is called in order whenever a bump rising edge
    is detected. Registering a handler also lazily activates my ROS subscriber.

    Calling register() with an already-registered handler is a no-op.

    Args:
        handler: Callable that accepts a list of bumper side strings
                 (e.g. ['left'] or ['center', 'right']).
        index:   Optional position in the chain; None means append.

    Note to self: Use functools.partial or a lambda to pre-bind parameters
    like custom distance/speed to do_backup before registering.
    """
    _ensure_subscriber()
    with _handlers_lock:
        if handler in _handlers:
            return
        if index is None:
            _handlers.append(handler)
        else:
            _handlers.insert(index, handler)


@api_call(default_verbosity=Verbosity.ACK)
def unregister(handler: Callable[[List[str]], None]) -> None:
    """Remove a handler from my chain.

    I silently do nothing if the handler is not currently registered.

    Args:
        handler: The exact callable previously passed to register().
    """
    with _handlers_lock:
        try:
            _handlers.remove(handler)
        except ValueError:
            pass


@api_call(default_verbosity=Verbosity.ACK)
def clear() -> None:
    """Remove all handlers from my chain, leaving it empty."""
    with _handlers_lock:
        _handlers.clear()


@api_call(default_verbosity=Verbosity.ACK)
def set_default() -> None:
    """Install my default bumper response: log the event, then back away.

    I clear the current chain and register [do_print, do_backup] in that order.
    This is a sensible safe baseline I can build on with additional handlers.
    """
    clear(verbosity=Verbosity.SILENT)
    register(do_stop, verbosity=Verbosity.SILENT)
    register(do_print, verbosity=Verbosity.SILENT)
    register(do_backup, verbosity=Verbosity.SILENT)


def show() -> None:
    """Print my current handler chain in execution order."""
    with _handlers_lock:
        if not _handlers:
            print("bumper: no handlers registered")
            return
        print("bumper: handler chain ({} handler{})".format(
            len(_handlers), 's' if len(_handlers) != 1 else ''))
        for i, h in enumerate(_handlers):
            print("  [{}] {}".format(i, getattr(h, '__name__', repr(h))))


# ---------------------------------------------------------------------------
# Atomic behaviors
# ---------------------------------------------------------------------------

def do_print(bumpers: List[str]) -> None:
    """Log which bumpers just fired.

    I'm the simplest possible handler — a good first entry in any chain for
    observability without side effects.

    Args:
        bumpers: List of side strings, e.g. ['left'] or ['center'].
    """
    print("bumper: BUMP — {}".format(' + '.join(bumpers)))


def do_stop(bumpers: List[str]) -> None:
    """Issue an emergency halt to my base.

    I publish zero velocities to Logos's safety mux slot for the fastest
    possible stop without outranking the Kobuki safety controller.

    Args:
        bumpers: Unused; present to satisfy handler signature.
    """
    from logos import base as _base
    _base.stop(topic='safety', verbosity=Verbosity.SILENT)


def do_backup(bumpers: List[str], distance: float = 0.3, speed: float = 0.2) -> None:
    """Back away from whatever I just bumped, steering to help clear the obstacle.

    I use the bumped side to pick a rotation direction: left contact steers me
    right during the reverse, right contact steers me left, and a center-only
    hit goes straight back. The rotation targets roughly 25 degrees over the
    backup distance — enough to swing clear of typical corner obstacles without
    over-rotating. I publish to Logos's safety mux slot so the command goes
    through even if normal navigation is paused, while still yielding to the
    Kobuki safety controller.

    Args:
        bumpers:  List of bumped side strings from the event.
        distance: How far to reverse in meters (default 0.30).
        speed:    Reverse speed in m/s (default 0.2).

    Note to self: To register a customised version, use functools.partial:
        register(functools.partial(do_backup, distance=0.25, speed=0.08))
    """
    from logos import base as _base

    duration = distance / max(speed, 0.01)  # + 0.5

    has_left = 'left' in bumpers
    has_right = 'right' in bumpers

    if has_left and has_right:
        angular_z = 0.0
    elif has_left:
        # Bumped left side — steer right (negative angular_z = clockwise)
        angular_z = -25.0 / duration
    elif has_right:
        # Bumped right side — steer left (positive angular_z = counterclockwise)
        angular_z = 25.0 / duration
    else:
        angular_z = 0.0

    _base.move_timed(
        linear_x=-speed,
        angular_z_deg=angular_z,
        duration=duration,
        topic='safety',
        verbosity=Verbosity.BRIEF,
    )


# ---------------------------------------------------------------------------
# Composed behaviors
# ---------------------------------------------------------------------------

def look_and_identify(bumpers: List[str]) -> Optional[str]:
    """Glance toward the bumped obstacle, classify it, and speak the result.

    I save my current pan/tilt angles, swing my gaze toward the bumped side and
    tilt down to floor level, run open-vocabulary detection on what I see, then
    restore my gaze to wherever I was looking before. I speak the result
    non-blocking so the rest of the handler chain can continue.

    Args:
        bumpers: List of bumped side strings from the event.

    Returns:
        The list of detected labels, or None if nothing was detected or
        vision was unavailable.

    Note to self: Add this after do_backup in the chain so I've already cleared
    the obstacle before trying to look at it.
    """
    from logos import pantilt as _pt
    from logos import vision as _vis
    from logos import models as _models
    from logos import emote as _emote

    prev_pan, prev_tilt = _pt.get_angles()

    print(f"Running logos.bumper.look_and_identify({bumpers})")
    has_left = 'left' in bumpers
    has_right = 'right' in bumpers

    if has_left and not has_right:
        pan = 30.0
        looking_at = "left"
    elif has_right and not has_left:
        pan = -30.0
        looking_at = "right"
    else:
        pan = 0.0
        looking_at = "front"

    print(f"Capturing pic of {looking_at} bumper area at pan-tilt ({pan}, -55) and running yoloe prompt-free detections...")
    _pt.move(pan, -55.0, verbosity=Verbosity.SILENT)
    import time; time.sleep(1.0)

    capture = _vis.capture(source='pan_tilt', save=True, verbosity=Verbosity.BRIEF)

    labels = None
    if capture is None:
        phrase = "I bumped into something but my camera isn't available. 😕"
    else:
        detections = _models.yoloe(capture.image)
        print(f"Top 3 yoloe detections — take with a grain of salt: {detections[:3]}")
        if detections:
            labels = list(dict.fromkeys(d.get('label', 'something') for d in detections))
            phrase = f"Oops, I may have nudged a {labels[0]} with my {looking_at} bumper! 😮"
        else:
            phrase = "Oops! I bumped into something but couldn't make out what. 🤔"

    print("Returning pan-tilt to starting position...")
    _pt.move(prev_pan, prev_tilt, verbosity=Verbosity.SILENT)
    _emote.ttp(phrase, engine='festival') # use festival for fast reactivity
    
    return labels


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

__all__ = [
    'register',
    'unregister',
    'clear',
    'set_default',
    'show',
    'do_print',
    'do_stop',
    'do_backup',
    'look_and_identify',
]
