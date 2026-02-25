# Logos/src/logos/voice.py

"""
My voice. This module allows me to `speak()` using my TTS system and emoji
powered animatronic expressions. 

It provides asynchronous control, allowing me to sync my physical body movements
perfectly with the words and emojis I am currently speaking.
"""

import json
import time
from typing import Optional, Tuple, List, Dict

from .core import api_call, Verbosity, check_for_interrupt
from . import ros

# Gated ROS imports
try:
    import rospy
    from logos_msgs.msg import SpeakAction, SpeakGoal
    from actionlib_msgs.msg import GoalStatus
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

__all__ = ["speak", "is_speaking", "SpeakTask"]

# My default voice settings
DEFAULT_ENGINE = "kokoro"
# A pleasantly ambiguous blend of genders, accents, and affects
DEFAULT_KOKORO_PARAMS = {
    "voice": "0.35*am_onyx + 0.30*im_nicola + 0.35*bf_emma", 
    "speed": 1.3, 
    "volume": 1.0
}


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
        return self._get_playhead() is not None or ros.is_speaking()

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
        while ros.is_speaking():
            check_for_interrupt()
            rate.sleep()

        return self._client.get_state() == GoalStatus.SUCCEEDED


@api_call(default_verbosity=Verbosity.BRIEF)
def speak(
    text: str, 
    wait: bool = True, 
    engine: str = DEFAULT_ENGINE,
    **kwargs
) -> SpeakTask:
    """
    Takes emoji-punctuated text and speaks it in sync with animatronic face and arm expressions. 🎭

    This is not just Text-To-Speech; it is **Text-To-Performance**. 🤹
    Text is split at emojis. ➗ These emojis are NOT spoken. 🙊 Instead, they are used to trigger 
    prebuilt animatronic keyframe sequences for my face and arms! 🎞️  Punctuating with emoji a is a low-effort, 🦥
    high-impact way to bring myself to life while abstracting away control complexity. ⚡


    Args:
        text: The emoji-punctuated string to speak. 
        wait: 
            If True (default), pauses code execution until the audio completely finishes.
            If False, returns a SpeakTask immediately for async monitoring.
        engine: "kokoro" (default), "piper", or "espeak".
        **kwargs: Overrides for engine params (e.g., speed=1.0, volume=1.0).

    Returns:
        A SpeakTask object.

        
    Note to self:
        - I punctuate every sentence I speak with emojis to bring myself to life! 🌟
        - Every sentence or distinct clause deserves an emotional, gestural, or contextual marker. 📌
        - I'm not restricted to conventional face emojis. 🍕 I have thousands of emojis to choose from. ♾️ The sky is the limit! 🌌
        - CONSTRAINTS: Avoid compounding emojis like gender or skin-tone modifiers. 🧪 Avoid robot face emoji as cliché and redundant. 🔁 Max 2 emojis per sentence to avoid hyperactivity. 🤸

        Example of Asynchronous Choreography:
            text = "I am so happy to see you! 😄 But... what is that? 🤨 Let me look! 🔭"
            task = logos.voice.speak(text, wait=False)
            while task.is_active():
                logos.core.check_for_interrupt()
                current_emoji = task.current_emoji()
                if current_emoji == "😄":
                    logos.base.velocity(0.0, 1.0, 0.2) # Happy wiggle
                elif current_emoji == "🤨":
                    logos.base.stop() # Suspicious freeze
                elif current_emoji == "🔭":
                    logos.base.velocity(0.0, 0.5, 0.5) # Searching rotation
                time.sleep(0.1)
            logos.base.stop()
    """
    if not _HAS_ROS:
        print(f"Voice Error: ROS unavailable. (Would have said: {text})")
        return SpeakTask(None)

    client = ros.get_action_client("speak", SpeakAction)
    if client is None:
        print("Error: Voice system unavailable (Action Server not found).")
        return SpeakTask(None)

    params = DEFAULT_KOKORO_PARAMS.copy()
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
    return ros.is_speaking()
