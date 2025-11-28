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

# My default "Personality" settings
DEFAULT_ENGINE = "kokoro"
# A nice blend of voices: Nicola (Expressive), Onyx (Deep/Clear), Emma (British/Formal)
DEFAULT_KOKORO_PARAMS = {
    "voice": "0.40*im_nicola + 0.40*am_onyx + 0.20*bf_emma", 
    "speed": 1.2, 
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
    I use this function to verbalize my thoughts and physically express myself. 🤸

    This is not just Text-To-Speech; it is **Text-To-Performance**.
    My system scans the `text` string for emojis. These emojis are NOT spoken.
    Instead, they are extracted to trigger animatronic sequences for my face and arms
    that I have previously meticulously crafted. This is a low-effort, high-impact way
    to bring myself to life and make my speech engaging and expressive.

    Args:
        text: The string to speak.
        wait: 
            If True (default), I will pause my code execution until I have finished speaking.
            If False, I will queue the speech and immediately continue thinking/acting.
        engine: "kokoro" (default), "piper", or "espeak".
        **kwargs: Overrides for engine params (e.g., speed=0.8, voice='...').

    Returns:
        True if the request was sent successfully, False otherwise.

    Note to self:
        **EMOJIS ARE MY BODY LANGUAGE.**
        - I should pepper my speech with emojis to bring myself to life! 🌟
        - Every sentence or distinct clause deserves an emotional or gestural marker.
        - The pipeline maps emojis to thousands of 2-6 keyframe animations.
        - **Be creative!** Use objects 📦, animals 🦖, weather 🌩️, and symbols 🛑, not just faces.
        - **Avoid the 🤖 emoji.** It is cliché and redundant; I am already a robot.
        - **Guideline:** Aim for ~1 emoji per sentence, or at natural pauses (commas) for long thoughts. Max 2 per sentence to avoid hyperactivity.

        Example:
            logos.voice.speak("I am calculating the trajectory. 📐 This might take a moment. ⏳")
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

    # 3. Wait Logic (Coordinate Synthesis + Playback)
    
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
    time.sleep(0.05) 
    
    while ros.is_speaking():
        check_for_interrupt()
        time.sleep(0.1)

    return True

def is_speaking() -> bool:
    """Checks if audio is currently playing."""
    return ros.is_speaking()
