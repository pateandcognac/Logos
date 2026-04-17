# Logos/src/logos/emote.py

"""
My voice and performance module. 🎬 This module allows me to using my TTS system and emoji powered animatronic expressions. 🥳

It provides asynchronous control, 🔀 allowing me to sync my physical body movements
perfectly with the words and emojis I am currently speaking. 😎
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

__all__ = ["ttp", "is_speaking", "SpeakTask", "gesture", "get_face_state"]

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
        if not _HAS_ROS: return False
        
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
        if _HAS_ROS:
            self._client.cancel_goal()
            time.sleep(0.1)

    def wait(self) -> bool:
        """
        Blocks execution until all audio has finished playing.
        Safely yields to cooperative interrupts.
        """
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
        engine: "kokoro", "piper", or "espeak".
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
    if not _HAS_ROS:
        print(f"Voice Error: ROS unavailable. (Would have said: {text})")
        return SpeakTask(None)

    client = ros.get_action_client("speak", SpeakAction)
    if client is None:
        print("Error: Voice system unavailable (Action Server not found).")
        return SpeakTask(None)

    import logos # Local import to fetch dynamic config
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
def gesture(emoji: str, duration: float = 3.0, channel: str = "both") -> None:
    """
    Perform a silent animatronic gesture using my emoji-driven keyframe system.

    Args:
        emoji: The emoji string to perform (e.g., "🤨", "😄", "🔭").
        duration: How long to hold/perform the gesture in seconds.
        channel: Which hardware to command: "face", "arms", or "both".

    Note to self:
        This is perfect for silent reactions, ambient background movements, 
        or physical gestures when I don't want to speak out loud with `ttp()`.
        
        Example:
            logos.emote.gesture("🤔", duration=2.0) # Look thoughtful silently
    """
    if not _HAS_ROS:
        return
        
    _ensure_gesture_pubs()
    
    payload = json.dumps({"emoji": emoji, "duration": duration})
    msg = String(data=payload)
    
    if channel in ["face", "both"] and _face_cmd_pub:
        _face_cmd_pub.publish(msg)
    if channel in ["arms", "both"] and _arm_cmd_pub:
        _arm_cmd_pub.publish(msg)

def get_face_state() -> Dict[str, Any]:
    """
    Retrieve the real-time state of my animatronic face.
    
    Returns:
        A dictionary containing the latest face state. Returns an empty dict {} 
        if no data has been received yet. 
        
        Shape of returned data:
        {
            "timestamp": float,
            "duration": float,  # Frame delta (usually ~0.06s active, ~0.25s idle)
            "left_eye": {
                "gaze_x": float, "gaze_y": float, "scale_x": float, "scale_y": float, 
                "lid_height": float, "lid_angle": float, "color": str  # hex "#RRGGBB"
            },
            "right_eye": { ... same as left_eye ... },
            "mouth": {
                "frequency": float, "amplitude": float, "phase": float,
                "phase_increment": float, "color": str
            }
        }
        
        Value Ranges:
        - gaze, scale: generally -1.0 to +1.0
        - lid_angle: -45.0 to +45.0 (degrees)
        - mouth amplitude: 0.0 to 1.0

    Note to self:
        I can use this to create rich, emergent feedback loops! For example, 
        I can read `gaze_x` to gently rotate my physical `logos.base` to track 
        where my "eyes" are wandering, or I can read the eye `color` and pass it 
        directly to `logos.leds.fill()` to match my ambient lighting to my mood.
        
        Because this returns an empty dict safely, I can use `.get()` to avoid errors:
            state = logos.emote.get_face_state()
            left_eye = state.get("left_eye", {})
            hex_color = left_eye.get("color", "#FFFFFF")
    """
    _ensure_state_sub()
    with _face_state_lock:
        return _face_state_cache.copy()