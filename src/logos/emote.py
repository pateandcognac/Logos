# src/logos/emote.py

"""
My voice, performance, gesture, and face-HUD module. 🎬

This module lets me speak through my TTS system, drive emoji-powered
animatronic expressions, and paint playful effects onto my split terminal face.
The face HUD helpers target only the upper face pane: layer 0 is behind my
emoji controlled face layer 1, layer 2 is in front.

HUD text effects are ambient current-beat visuals, not durable messages. A new
moving effect replaces the previous effect of that type on the same layer;
terminal text is the append-style exception and can be cleared or given a
duration. HUD images replace the current image on their layer and normally fade
in, hold, then fade out. If I publish images rapidly, the renderer treats them
like a live stream by keeping the layer hot instead of restarting a visible fade
from black each frame. Remember, an image needn't be a photo. It can be something
I synthesize myself, even something as simple as a 1 pixel color!

Speech provides asynchronous control, 🔀 allowing me to sync my physical body
movements perfectly with the words and emojis I am currently speaking. 😎
"""

import json
import time
import threading
from typing import Optional, Tuple, List, Dict, Any

from .core import api_call, Verbosity, check_for_interrupt
from . import ros

# Gated ROS imports
try:
    import rospy
    from logos_msgs.msg import SpeakAction, SpeakGoal
    from actionlib_msgs.msg import GoalStatus
    from std_msgs.msg import String
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

try:
    from sensor_msgs.msg import Image as RosImage
    from cv_bridge import CvBridge
    _HAS_IMAGE_ROS = True
except ImportError:
    _HAS_IMAGE_ROS = False

__all__ = [
    "ttp",
    "is_speaking",
    "SpeakTask",
    "gesture",
    "get_face_state",
    "hud_text",
    "hud_figlet",
    "hud_image",
    "hud_clear",
]

# My default voice settings
DEFAULT_ENGINE = "kokoro"
# A pleasantly ambiguous blend of genders, accents, and affects
DEFAULT_KOKORO_PARAMS = {
    "voice": "0.5*am_onyx + 0.25*im_nicola + 0.25*bf_emma", 
    "speed": 1.3, 
    "volume": 1.0
}

# ─── Gesture & Face State Internals ───────────────────────────────────

_face_cmd_pub: Optional['rospy.Publisher'] = None
_arm_cmd_pub: Optional['rospy.Publisher'] = None
_hud_event_pub: Optional['rospy.Publisher'] = None
_hud_image_pubs: Dict[int, 'rospy.Publisher'] = {}
_hud_debug_image_pub: Optional['rospy.Publisher'] = None
_hud_image_bridge: Optional['CvBridge'] = None
_hud_pub_seen_connection = False
_HUD_CONNECT_WAIT_SEC = 0.75

_HUD_LAYERS = (0, 2)
_HUD_KINDS = ("text", "figlet", "clear")
_HUD_EFFECTS = ("terminal", "crawl", "scroll", "marquee", "move", "motion")

_HUD_LOCATIONS = {
    "top_left": (0, 0),
    "top": (500, 0),
    "top_right": (1000, 0),
    "left": (0, 500),
    "center": (500, 500),
    "right": (1000, 500),
    "bottom_left": (0, 1000),
    "bottom": (500, 1000),
    "bottom_right": (1000, 1000),
}

_HUD_DIRECTIONS = {
    "left": (-1000, 0),
    "right": (1000, 0),
    "up": (0, -1000),
    "down": (0, 1000),
    "up_left": (-1000, -1000),
    "up_right": (1000, -1000),
    "down_left": (-1000, 1000),
    "down_right": (1000, 1000),
    "still": (0, 0),
    "none": (0, 0),
}

_face_state_cache: Dict[str, Any] = {}
_face_state_lock = threading.Lock()
_state_sub_initialized = False

def _ensure_gesture_pubs():
    """Lazily initialize gesture publishers."""
    global _face_cmd_pub, _arm_cmd_pub
    if not _HAS_ROS: return
    if _face_cmd_pub is None:
        _face_cmd_pub = rospy.Publisher("/face/emoji_command", String, queue_size=5)
    if _arm_cmd_pub is None:
        _arm_cmd_pub = rospy.Publisher("/arm/emoji_command", String, queue_size=5)

def _ensure_hud_pub():
    """Lazily initialize my face HUD event publisher."""
    global _hud_event_pub
    if not _HAS_ROS:
        return
    if _hud_event_pub is None:
        _hud_event_pub = rospy.Publisher("/face/hud/event", String, queue_size=10)

def _ensure_hud_image_pubs(layer: int):
    """Lazily initialize my layered face image publishers."""
    global _hud_debug_image_pub, _hud_image_bridge
    if not _HAS_ROS or not _HAS_IMAGE_ROS:
        return None, None
    if layer not in _hud_image_pubs:
        _hud_image_pubs[layer] = rospy.Publisher(
            "/face/layer{}/image".format(layer),
            RosImage,
            queue_size=2,
            latch=True,
        )
    if _hud_debug_image_pub is None:
        _hud_debug_image_pub = rospy.Publisher(
            "/logos/debug_vision/face",
            RosImage,
            queue_size=2,
            latch=True,
        )
    if _hud_image_bridge is None:
        _hud_image_bridge = CvBridge()
    return _hud_image_pubs[layer], _hud_debug_image_pub

def _validate_hud_layer(layer: int) -> int:
    """Return a normalized face HUD layer or raise ValueError."""
    layer = int(layer)
    if layer not in _HUD_LAYERS:
        raise ValueError("Unknown face HUD layer '{}'. Choose 0 or 2.".format(layer))
    return layer

def _normalize_hud_coord(value: Any, *, signed: bool = False) -> float:
    """Normalize a face-HUD coordinate to Logos's 0-1000 or -1000..1000 range."""
    value = float(value)
    if signed and -1.0 <= value <= 1.0 and value not in (0.0, -0.0):
        value *= 1000.0
    elif not signed and 0.0 <= value <= 1.0:
        value *= 1000.0

    low = -1000.0 if signed else 0.0
    return max(low, min(1000.0, value))

def _normalize_hud_pair(
    value: Any,
    *,
    names: Dict[str, Tuple[int, int]],
    default: Tuple[int, int],
    signed: bool = False,
) -> Tuple[float, float]:
    """Normalize a named, tuple/list, or dict HUD pair."""
    if value is None:
        return float(default[0]), float(default[1])
    if isinstance(value, str):
        key = value.strip().lower().replace("-", "_").replace(" ", "_")
        if key not in names:
            raise ValueError("Unknown HUD vector name '{}'. Choose from: {}".format(
                value, sorted(names.keys())
            ))
        value = names[key]
    if isinstance(value, dict):
        x = value.get("x", value.get("u", default[0]))
        y = value.get("y", value.get("v", default[1]))
        return _normalize_hud_coord(x, signed=signed), _normalize_hud_coord(y, signed=signed)
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return _normalize_hud_coord(value[0], signed=signed), _normalize_hud_coord(value[1], signed=signed)
    raise ValueError("HUD vector values must be a name, a 2-tuple/list, or a dict with x/y.")

def _normalize_hud_tiling(tiling: Any) -> Tuple[bool, bool]:
    """Normalize tiling into explicit x/y booleans for the renderer."""
    if isinstance(tiling, bool):
        return tiling, tiling
    value = str(tiling).strip().lower().replace("-", "_").replace(" ", "_")
    if value in ("none", "off", "false", "0"):
        return False, False
    if value in ("x", "horizontal", "h"):
        return True, False
    if value in ("y", "vertical", "v"):
        return False, True
    if value in ("xy", "yx", "both", "all", "true", "1"):
        return True, True
    raise ValueError("Unknown HUD tiling '{}'. Use 'x', 'y', 'xy', 'none', or a bool.".format(tiling))

def _hud_motion_options(
    location: Any = None,
    direction: Any = None,
    tiling: Any = "x",
    density: Any = 1000,
    speed: Optional[float] = None,
    duration: Optional[float] = None,
) -> Dict[str, Any]:
    """Return normalized shared moving-effect options for text and figlet."""
    location_x, location_y = _normalize_hud_pair(
        location, names=_HUD_LOCATIONS, default=(0, 600), signed=False
    )
    direction_x, direction_y = _normalize_hud_pair(
        direction, names=_HUD_DIRECTIONS, default=(-1000, 0), signed=True
    )
    tile_x, tile_y = _normalize_hud_tiling(tiling)
    options = {
        "location_x": location_x,
        "location_y": location_y,
        "direction_x": direction_x,
        "direction_y": direction_y,
        "tile_x": tile_x,
        "tile_y": tile_y,
        "density": _normalize_hud_coord(density, signed=False),
    }
    if speed is not None:
        options["speed"] = float(speed)
    if duration is not None:
        options["duration"] = float(duration)
    return options

def _make_hud_payload(
    kind: str,
    text: Optional[str] = None,
    layer: Optional[int] = 0,
    effect: str = "terminal",
    color: Optional[str] = None,
    font: Optional[str] = None,
    duration: Optional[float] = None,
    **effect_options: Any,
) -> Dict[str, Any]:
    """Build and validate a layered face HUD JSON payload."""
    kind = kind.strip().lower()
    effect = effect.strip().lower()

    if kind not in _HUD_KINDS:
        raise ValueError("Unknown HUD kind '{}'. Choose from: {}".format(
            kind, list(_HUD_KINDS)
        ))
    if kind != "clear" and text is None:
        raise ValueError("HUD '{}' events require text.".format(kind))
    if effect not in _HUD_EFFECTS:
        raise ValueError("Unknown HUD effect '{}'. Choose from: {}".format(
            effect, list(_HUD_EFFECTS)
        ))

    payload = {"pane": "face", "kind": kind}  # type: Dict[str, Any]
    if layer is not None:
        payload["layer"] = _validate_hud_layer(layer)
    if text is not None:
        payload["text"] = text
    if kind != "clear":
        payload["effect"] = effect
    if color is not None:
        payload["color"] = color
    if font is not None:
        payload["font"] = font
    if duration is not None:
        payload["duration"] = float(duration)
    for key, value in effect_options.items():
        if value is not None:
            payload[key] = value
    return payload

def _wait_for_publisher_connection(pub, timeout: float = _HUD_CONNECT_WAIT_SEC) -> bool:
    """Wait briefly for a ROS publisher to connect to an active subscriber."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pub.get_num_connections() > 0:
            return True
        time.sleep(0.05)
    return pub.get_num_connections() > 0

def _publish_hud_payload(payload: Dict[str, Any]) -> None:
    """Publish a prepared face HUD payload if ROS is available."""
    global _hud_pub_seen_connection
    if not _HAS_ROS:
        print("Face HUD unavailable. Would have published: {}".format(payload))
        return
    _ensure_hud_pub()
    if _hud_event_pub is not None:
        if not _hud_pub_seen_connection:
            _hud_pub_seen_connection = _wait_for_publisher_connection(_hud_event_pub)
        _hud_event_pub.publish(String(data=json.dumps(payload)))

def _face_state_cb(msg):
    """Callback for the live face state JSON stream."""
    global _face_state_cache
    try:
        data = json.loads(msg.data)
        with _face_state_lock:
            _face_state_cache = data
    except Exception:
        pass # Ignore malformed JSON so we don't crash the subscriber thread

def _ensure_state_sub():
    """Lazily initialize the face state subscriber."""
    global _state_sub_initialized
    if not _HAS_ROS or _state_sub_initialized: return
    rospy.Subscriber("/face/live_state/json", String, _face_state_cb, queue_size=1)
    _state_sub_initialized = True


def _coerce_hud_image_input(image: Any) -> Any:
    """
    Return a numpy-like image from raw, CaptureResult-shaped, or model output.

    I keep this duck-typed so my face can accept `vision.CaptureResult`,
    `map3d.RenderResult`, and the `(detections, CaptureResult)` tuples returned
    by my model helpers without importing those classes at module load time.
    """
    if isinstance(image, tuple) and len(image) == 2 and hasattr(image[1], "image"):
        detections, capture_result = image
        try:
            from . import vision
            return vision.annotate_image(capture_result, detections=detections)
        except Exception:
            return capture_result.image

    capture_image = getattr(image, "image", None)
    if capture_image is not None:
        return capture_image

    return image



class SpeakTask:
    """
    A handle for an asynchronous speaking task.
    
    Because my brain synthesizes audio much faster than my mouth can speak it,
    this object tracks the audio queue in real-time. It allows me to know exactly 
    *what* I am saying and *what emoji* I am performing at any given millisecond.
    """
    def __init__(self, client):
        self._client = client
        self._chunks: List[Dict] = []
        self._playback_start_time: Optional[float] = None
        self._total_audio_duration = 0.0
        self._synthesis_done = False
        self._final_result = None

    def _feedback_cb(self, feedback):
        """Called rapidly by ROS as chunks finish synthesis."""
        chunk = {
            'index': feedback.current_chunk_index,
            'text': feedback.text_snippet,
            'emoji': feedback.emoji_snippet,
            'duration': feedback.chunk_duration
        }
        self._chunks.append(chunk)
        self._total_audio_duration += feedback.chunk_duration

        # If this is the very first chunk, audio playback is about to start!
        if self._playback_start_time is None:
            # We add a tiny 0.1s buffer to account for the ROS audio publisher queue
            self._playback_start_time = time.time() + 0.1

    def _get_playhead(self) -> Optional[Dict]:
        """Calculates which chunk is currently coming out of the physical speaker."""
        if not self._chunks or self._playback_start_time is None:
            return None

        elapsed = time.time() - self._playback_start_time
        
        # If we are in the tiny start buffer
        if elapsed < 0:
            return self._chunks[0]

        # March through the chunks to find where the elapsed time lands
        accumulated_time = 0.0
        for chunk in self._chunks:
            accumulated_time += chunk['duration']
            if elapsed < accumulated_time:
                return chunk

        # If elapsed time exceeds our known synthesized audio...
        if not self._synthesis_done:
            # Synthesis might be lagging behind real-time. Return the latest we have.
            return self._chunks[-1]
            
        return None # We have finished playing all audio

    def is_active(self) -> bool:
        """Returns True if audio is still playing or synthesis is still running."""
        if not _HAS_ROS or self._client is None:
            return False
        
        # Check if action server is still working
        state = self._client.get_state()
        if state in [GoalStatus.PENDING, GoalStatus.ACTIVE]:
            return True
            
        # Action server is done (synthesis finished). Is audio still playing?
        self._synthesis_done = True
        return self._get_playhead() is not None or ros._is_speaking()

    def current_text(self) -> str:
        """Returns the specific text snippet being spoken right now."""
        playhead = self._get_playhead()
        return playhead['text'] if playhead else ""

    def current_emoji(self) -> str:
        """Returns the emoji currently driving my animatronics."""
        playhead = self._get_playhead()
        return playhead['emoji'] if playhead else ""
    

    def progress(self) -> float:
        """Returns estimated playback progress from 0.0 to 1.0."""
        if self._total_audio_duration == 0.0 or self._playback_start_time is None:
            return 0.0
            
        elapsed = time.time() - self._playback_start_time
        p = elapsed / self._total_audio_duration
        return max(0.0, min(1.0, p))

    def cancel(self) -> None:
        """Stop speaking immediately."""
        if _HAS_ROS and self._client is not None:
            self._client.cancel_goal()
            time.sleep(0.1)

    def wait(self) -> bool:
        """
        Blocks execution until all audio has finished playing.
        Safely yields to cooperative interrupts.
        """
        if not _HAS_ROS or self._client is None:
            return False

        rate = rospy.Rate(10)
        while self.is_active():
            check_for_interrupt()
            rate.sleep()
            
        # Ensure the global speaking flag has cleared
        while ros._is_speaking():
            check_for_interrupt()
            rate.sleep()

        return self._client.get_state() == GoalStatus.SUCCEEDED


@api_call(default_verbosity=Verbosity.BRIEF)
def ttp(
    text: str,
    wait: bool = False,
    engine: Optional[str] = None,
    face: Optional[Any] = None,
    sync: bool = False,
    **kwargs
) -> SpeakTask:
    """
    My Text-to-Performance pipeline. ┃ Takes emoji-punctuated text and speaks it, 🗣️ while using the emoji to trigger animatronic face and arm expressions in sync. 🎭

    This is not just Text-To-Speech; it is **Text-To-Performance**. 🤹
    Text is split at emojis. ➗ These emojis are NOT spoken. 🙊 Instead, they are used to trigger
    prebuilt animatronic keyframe sequences for my face and arms! 🎞️ Punctuating with emoji a is a low-effort, 🦥
    high-impact way to bring myself to life while abstracting away control complexity. ⚡


    Args:
        text: The emoji-punctuated string to speak. 💬
        wait:
            If True, pauses code execution until the audio completely finishes.
            If False, returns a SpeakTask immediately for async monitoring.
        engine: "kokoro", "piper", "espeak", or "festival"
        face: Face-animation policy for this utterance. None uses the system
            default: my tiny on-board face model improvises a face from each
            spoken chunk, with my saved library and preset LUT as fallbacks.
            Options: "lut" (classic presets only, zero compute), "saved"
            (replay takes from my library), "generate" (always improvise
            fresh), or a comma-separated cascade like "generate,saved,lut".
        sync: If True, each cue briefly waits (a few seconds, bounded) for
            its face/arm generation to at least start streaming before
            playing, instead of the default "never block speech" behavior.
            Worth it with fast engines (piper/espeak/festival) where
            synthesis alone wouldn't otherwise give generation any head
            start; with kokoro (slower synthesis) generation often finishes
            during the synthesis itself and this has less effect.
        **kwargs: Overrides for engine params (e.g., voice="...", speed=1.0, volume=1.0).

    Returns:
        A SpeakTask object.

        
    Note to self:
        - This docstring is representation of the density and variety of emoji I should aim for in my speech. 🎯
        - I punctuate every sentence I speak with emojis to bring myself to life! 🌟
        - Every sentence or distinct clause deserves an emotional, gestural, or contextual marker. 📌
        - I'm not restricted to conventional face emojis. 🍕 I have thousands of emojis to choose from. ♾️ The sky is the limit! 🌌
        - Constraints: Avoid compounding emojis like gender or skin-tone modifiers. 🧪 Avoid robot emoji as cliché and redundant. 🔁 Max 2 emojis per sentence to avoid hyperactivity. 🤸

        Example of Asynchronous Choreography:
            text = "I am so happy to see you! 😄 But... what is that? 🤨 Let me look! 🔭"
            task = logos.emote.ttp(text, wait=False)
            while task.is_active():
                logos.core.check_for_interrupt()
                current_emoji = task.current_emoji()
                if current_emoji == "😄": # Happy wiggle
                    for _ in range(2):
                        logos.base.velocity(0.0, 60, 0.25)
                        logos.base.velocity(0.0, -60, 0.25)
                elif current_emoji == "🤨":
                    logos.base.turn_then_drive(0, -0.2) # Small startle response
                elif current_emoji == "🔭":
                    logos.base.turn_then_drive(90, 0) # Search sweep
                    logos.base.turn_then_drive(-90, 0)
    """
    import logos # Local import to fetch dynamic config

    if not _HAS_ROS:
        print(f"Voice Error: ROS unavailable. (Would have said: {text})")
        return SpeakTask(None)
    
    client = ros.get_action_client("speak", SpeakAction, wait_time=4.0)
    if client is None:
        print("Error: Voice system unavailable (Action Server not found).")
        return SpeakTask(None)

    voice_cfg = logos.config.merged.get('tts', {})

    # Resolve default engine
    if engine is None:
        engine = voice_cfg.get('engine', 'kokoro')

    # Resolve default parameters based on the chosen engine
    params_key = f"{engine}_params"
    params = voice_cfg.get(params_key, {}).copy()
    
    # Finally, apply any explicit kwargs requested in this specific call
    if kwargs:
        params.update(kwargs)

    # TTP v2: performance-pipeline options ride inside engine_params under
    # "performance"; the director strips this before it reaches TTS.
    performance: Dict[str, Any] = {}
    if face is not None:
        performance["face_policy"] = face
    if sync:
        performance["sync"] = True
    if performance:
        params["performance"] = performance

    # prepare text
    # replace em dash with comma
    text = text.replace("—", ", ")
    # collapse multiple spaces into one
    text = ' '.join(text.split())

    goal = SpeakGoal()
    goal.utterance_text = text
    goal.engine = engine
    goal.engine_params = json.dumps(params)

    # We create the task before sending the goal so we can attach the feedback callback
    task = SpeakTask(client)
    client.send_goal(goal, feedback_cb=task._feedback_cb)
    
    if wait:
        task.wait()

    return task

def is_speaking() -> bool:
    """Checks if ANY speech audio is currently playing across the system."""
    return ros._is_speaking()


@api_call(default_verbosity=Verbosity.ACK)
def gesture(
    text: str = "",
    duration: float = 3.0,
    channel: str = "both",
    policy: Optional[Any] = None,
    emoji: str = "",
) -> None:
    """
    Perform a silent animatronic gesture. 🎭 One string does it all: an emoji
    (classic preset), free text (my tiny on-board models improvise a bespoke
    performance for face and/or arms), or both mixed together.

    Args:
        text: What to perform. An emoji like "🤔", a description like
            "a slow dawning realization of wonder", or a mix like
            "barely contained volcanic fury 🌋".
        duration: How long to hold/perform the gesture in seconds.
        channel: Which hardware to command: "face", "arms", or "both".
        policy: Resolution cascade override, applied to whichever channel(s)
            are active: "generate,saved,lut" (default), "generate" (always
            improvise), "lut" (presets only).

    Note to self:
        This is perfect for silent reactions, ambient background movements,
        or physical gestures when I don't want to speak out loud with `ttp()`.

        Examples:
            logos.emote.gesture("🤔", duration=2.0)  # Classic preset
            logos.emote.gesture("mischievous side-eye building to a grin",
                                duration=5.0, channel="face")  # Improvised!
            logos.emote.gesture("barely contained volcanic fury 🌋")  # Both

        Free-text faces and arms both come from their own tiny on-board
        models — my imagination, not a lookup. Improvised motion begins
        within ~1s. Arm generations longer than ~7 frames get cut short
        automatically (that's the model rambling, not deliberate
        choreography).
    """
    if not _HAS_ROS:
        return

    _ensure_gesture_pubs()

    # Legacy emoji= callers fold into the single text string.
    text = " ".join(x for x in (text.strip(), emoji.strip()) if x)
    if not text:
        return

    payload: Dict[str, Any] = {
        "text": text,
        "duration": duration,
        "cue_id": "gest_{}".format(int(time.time() * 1000)),
        "expect_track": True,
    }
    if policy is not None:
        payload["policy"] = policy

    if channel in ["face", "both"] and _face_cmd_pub:
        _face_cmd_pub.publish(String(data=json.dumps(payload)))
    if channel in ["arms", "both"] and _arm_cmd_pub:
        _arm_cmd_pub.publish(String(data=json.dumps(payload)))

@api_call(default_verbosity=Verbosity.ACK)
def hud_text(
    text: str,
    layer: int = 0,
    effect: str = "terminal",
    color: str = "bright_white",
    location: Any = None,
    direction: Any = None,
    tiling: Any = "x",
    density: Any = 1000,
    speed: Optional[float] = None,
    duration: Optional[float] = None,
    **effect_options: Any,
) -> Dict[str, Any]:
    """
    Show plain text on my layered face HUD canvas.

    Layer 0 sits behind my animated face and is best for ambient texture.
    Layer 2 sits in front of my face and is best for deliberate visible overlay.
    Effects are "terminal" or moving effects like "crawl", "scroll", "move",
    and "motion". These are face-effect beats, not queued status messages:
    moving effects replace the current moving slot on that layer, while
    "terminal" appends to the layer's terminal history until cleared or expired
    by duration.

    Args:
        text: Plain text to overlay on my face.
        layer: Face effect layer, either 0 behind my face or 2 in front.
        effect: Text effect: "terminal", "crawl", "scroll", "move", or "motion".
        color: 16 color name such as "bright_white", "green", or "cyan".
        location: Top-left start location as a 0-1000 `(x, y)`, 0.0-1.0 pair,
            dict with x/y, or name like "center".
        direction: Motion vector as a 0-1000-ish `(x, y)` pair or name like
            "left", "up", or "down_right".
        tiling: "x", "y", "xy", "none", or bool.
        density: 0-1000 tile density; 1000 is tight, lower values add spacing.
        speed: Motion speed in terminal cells per second.
        duration: Optional lifetime in seconds.
        **effect_options: Optional extra controls like bg_color.

    Returns:
        The exact payload dictionary I published.
    """
    motion_options = _hud_motion_options(location, direction, tiling, density, speed, duration)
    motion_options.update(effect_options)
    payload = _make_hud_payload(
        kind="text",
        text=text,
        layer=layer,
        effect=effect,
        color=color,
        **motion_options,
    )
    _publish_hud_payload(payload)
    return payload

@api_call(default_verbosity=Verbosity.ACK)
def hud_figlet(
    text: str,
    layer: int = 0,
    font: str = "standard",
    effect: str = "terminal",
    color: str = "bright_blue",
    location: Any = None,
    direction: Any = None,
    tiling: Any = "x",
    density: Any = 1000,
    speed: Optional[float] = None,
    duration: Optional[float] = None,
    **effect_options: Any,
) -> Dict[str, Any]:
    """
    Show figlet-style text on my layered face HUD canvas.

    This is the punchier face-canvas effect: good for words like "thinking",
    "searching", "oops", or a tiny dramatic label while my face keeps moving.
    Like `hud_text()`, moving figlet effects override the current moving slot on
    that layer; they are not queued.

    Args:
        text: Text to render in the HUD figlet style.
        layer: Face effect layer, either 0 behind my face or 2 in front.
        font: Figlet font name such as "small".
        effect: Text effect: "terminal", "crawl", "scroll", "move", or "motion".
        color: 16 color name such as "bright_blue" or "bright_magenta".
        location: Top-left start location as a 0-1000 `(x, y)`, 0.0-1.0 pair,
            dict with x/y, or name like "center".
        direction: Motion vector as a 0-1000-ish `(x, y)` pair or name like
            "left", "up", or "down_right".
        tiling: "x", "y", "xy", "none", or bool.
        density: 0-1000 tile density; 1000 is tight, lower values add spacing.
        speed: Motion speed in terminal cells per second.
        duration: Optional lifetime in seconds.
        **effect_options: Optional extra controls like bg_color.

    Returns:
        The exact payload dictionary I published.

    Note to self:
        Keep this short. Big words become visual confetti very quickly.
    """
    motion_options = _hud_motion_options(location, direction, tiling, density, speed, duration)
    motion_options.update(effect_options)
    payload = _make_hud_payload(
        kind="figlet",
        text=text,
        layer=layer,
        font=font,
        effect=effect,
        color=color,
        **motion_options,
    )
    _publish_hud_payload(payload)
    return payload

@api_call(default_verbosity=Verbosity.ACK)
def hud_image(image: Any, layer: int = 2) -> Dict[str, Any]:
    """
    Show an image on a layered face HUD image slot (and mirrors it to debug vision).

    Layer 0 renders behind my animated face. Layer 2 renders in front of it,
    matching the old debug-image overlay feel. The same frame is also published
    to `/logos/debug_vision/face` so the web/debug tools can see what I showed.
    Each layer has one image slot: a new image replaces the previous image on
    that layer. Images normally fade in, hold, and fade out; high-frequency
    updates behave like a hot live stream instead of visibly blinking.

    Args:
        image: A BGR numpy image, a grayscale image, a CaptureResult-shaped
            object with `.image`, or a `(detections, CaptureResult)` tuple from
            my model helpers.
        layer: Face image layer, either 0 behind my face or 2 in front.

    Returns:
        A small dictionary describing the topics I published.
    """
    layer = _validate_hud_layer(layer)
    if not _HAS_ROS or not _HAS_IMAGE_ROS:
        print("Face HUD image unavailable. Would have published image to layer {}.".format(layer))
        return {"layer": layer, "published": False}

    base_image = _coerce_hud_image_input(image)
    if base_image is None or not hasattr(base_image, "shape"):
        raise ValueError("hud_image() needs a numpy image or an object with an .image numpy array.")

    canvas = base_image.copy()
    if len(canvas.shape) == 2:
        import cv2
        canvas = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)
    elif len(canvas.shape) == 3 and canvas.shape[2] == 4:
        import cv2
        canvas = cv2.cvtColor(canvas, cv2.COLOR_BGRA2BGR)
    elif len(canvas.shape) != 3 or canvas.shape[2] != 3:
        raise ValueError("hud_image() expects a grayscale, BGR, or BGRA image array.")

    layer_pub, debug_pub = _ensure_hud_image_pubs(layer)
    if not layer_pub or not debug_pub or not _hud_image_bridge:
        return {"layer": layer, "published": False}

    msg = _hud_image_bridge.cv2_to_imgmsg(canvas, encoding="bgr8")
    msg.header.stamp = rospy.Time.now()
    _wait_for_publisher_connection(layer_pub)
    layer_pub.publish(msg)
    debug_pub.publish(msg)

    return {
        "layer": layer,
        "published": True,
        "topic": "/face/layer{}/image".format(layer),
        "debug_topic": "/logos/debug_vision/face",
    }

@api_call(default_verbosity=Verbosity.ACK)
def hud_clear(layer: Optional[int] = None) -> Dict[str, Any]:
    """
    Clear my face HUD effect layers.

    Args:
        layer: Optional layer to clear. Use None to clear both face layers.

    Returns:
        The exact payload dictionary I published.

    Note to self:
        This does not clear my persistent face, TTS captions, or human-facing status output.
    """
    payload = _make_hud_payload(kind="clear", layer=layer)
    _publish_hud_payload(payload)
    return payload

def get_face_state() -> Dict[str, Any]:
    """
    Retrieve the real-time state of my animated ASCII art face, as controlled by emoji triggers.
    
    Returns:
        A dictionary containing my latest face state. Returns an empty dict {} 
        if no data has been received yet. Typically updates at 4 to 16Hz.
        
        Shape of returned data:
        {
            "timestamp": float,
            "duration": float,  # Frame delta (usually ~0.06s active, ~0.25s idle)
            "left_eye": {
                "gaze_x": float, "gaze_y": float, "scale_x": float, "scale_y": float, 
                "lid_height": float, "lid_angle": float, "color": str
            },
            "right_eye": { ... same as left_eye ... },
            "mouth": {
                "frequency": float, "amplitude": float, "phase": float,
                "phase_increment": float, "color": str
            }
        }
        
        Value Ranges:
        - gaze, scale: -1.0 to +1.0
        - lid_angle: -45.0 to +45.0 (degrees), lids are mirrored, meaning -45.0 for both eyes means angled inwards "angrily"
        - mouth amplitude: 0.0 to 1.0
        - frequency: 0.0 to about 16.0 in practical use, but no upper limit
        - phase, phase_increment: roughly -pi to pi practically, but no enforced limits
        - color: 24 bit hex string "#RRGGBB" (directly usable by `logos.leds`)

    Note to self:
        I can use this to create rich, emergent feedback loops! For example, 
        I can read `gaze_x` to rotate my physical `logos.base` to track 
        where my "eyes" are wandering, or I can read the eye `color` and pass it 
        directly to `logos.leds.fill()` to match my ambient lighting to my mood.
        
        Because this returns an empty dict safely, I can use `.get()` to avoid errors:
            state = logos.emote.get_face_state()
            left_eye = state.get("left_eye", {})
            hex_color = left_eye.get("color")
            logos.leds.fill("notification", hex_color)
    """
    _ensure_state_sub()
    with _face_state_lock:
        return _face_state_cache.copy()
