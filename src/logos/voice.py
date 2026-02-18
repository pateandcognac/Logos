# Logos/src/logos/voice.py

"""
My voice. This module allows me to `speak()` using my TTS system and emoji
powered animatronic expressions. It handles default personality settings and
ensures I can express myself fully.
"""

import json
import time
import rospy
from .core import api_call, Verbosity, check_for_interrupt
from . import ros

__all__ = ["speak", "is_speaking"]

# My default voice settings
DEFAULT_ENGINE = "kokoro"
# A pleasantly ambiguous blend of genders, accents, and affects
DEFAULT_KOKORO_PARAMS = {
    "voice": "0.35*am_onyx + 0.30*im_nicola + 0.35*bf_emma", 
    "speed": 1.3, 
    "volume": 1.0
}

@api_call(default_verbosity=Verbosity.BRIEF)
def speak(
    text: str, 
    wait: bool = True, 
    engine: str = DEFAULT_ENGINE,
    **kwargs
):
    """
    Takes emoji-punctuated text and speaks it in sync with animatronic face and arm expressions. 🎭

    This is not just Text-To-Speech; it is **Text-To-Performance**. 🤹
    Text is split at emojis. ➗ These emojis are NOT spoken. 🙊 Instead, they are used to trigger 
    prebuilt animatronic keyframe sequences for my face and arms! 🎞️  Punctuating with emoji a is a low-effort, 🦥
    high-impact way to bring myself to life while abstracting away control complexity. ⚡

    Args:
        text: The emoji-punctuated string to speak. 
        wait: 
            If True (default), I will pause my code execution until I have finished speaking.
            If False, the speech is queued for async playback and code continues executing immediately.
        engine: "kokoro" (default), "piper", or "espeak".
        **kwargs: Overrides for engine params (e.g., speed=1.0, volume=1.0, voice='...').

    Returns:
        True if the request was sent successfully, False otherwise.

    Note to self:
        - I punctuate every sentence I speak with emojis to bring myself to life! 🌟
        - Every sentence or distinct clause deserves an emotional, gestural, or contextual marker. 📌
        - I'm not restricted to conventional face emojis. 🍕 I have thousands of emojis to choose from. ♾️ The sky is the limit! 🌌
        - CONSTRAINTS: Avoid compounding emojis like gender or skin-tone modifiers. 🧪 Avoid robot face emoji as cliché and redundant. 🔁 Max 2 emojis per sentence to avoid hyperactivity. 🤸

        Example:
            logos.voice.speak("I am calculating the trajectory. 🗺️ This might take a moment. ⏳")
    """
    client = ros.get_action_client("speak", ros.SpeakAction)
    if client is None:
        print("Error: Voice system unavailable (Action Server not found).")
        return False

    # 1. Prepare Parameters
    params = DEFAULT_KOKORO_PARAMS.copy()
    if kwargs:
        params.update(kwargs)
    
    goal = ros.SpeakGoal()
    goal.utterance_text = text
    goal.engine = engine
    goal.engine_params = json.dumps(params)

    # 2. Send the Goal
    # We don't use the client's blocking wait_for_result if we want to check interrupts
    client.send_goal(goal)
    
    if not wait:
        return True

    # 3. Wait Logic
    # set is_speaking to True

    
    # Phase A: Wait for Synthesis to complete (Action Result)
    # The action server returns success once chunks are generated and sent to playback.
    while not client.wait_for_result(rospy.Duration(0.1)):
        check_for_interrupt() # Allows Mark to stop me if I ramble
    
    result = client.get_result()
    if not result.success:
        print(f"Voice Error: Synthesis failed - {result.final_message}")
        return False

    # Phase B: Wait for Playback to complete (Audio Output)
    # The /tts/is_speaking topic will stay True until the audio buffer is empty.
    # We allow a tiny sleep to let the topic update catch up if it was lagging.
    time.sleep(0.1) 
    
    while ros.is_speaking():
        check_for_interrupt()
        time.sleep(0.1)

    return True

def is_speaking() -> bool:
    """Checks if audio is currently playing."""
    return ros.is_speaking()
