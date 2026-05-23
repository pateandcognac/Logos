# src/skills/social.py

"""
Social and expressive behaviors. 🎭

This module contains skills designed to make me more expressive, engaging, 
and lifelike during human interactions. It translates my internal states 
into physical body language using the pan-tilt head, base wiggles, and LEDs.
"""

import time
from typing import Tuple, Optional
import logos
from logos.core import verbosity, Verbosity

def expressive_gaze(
    pos1: Tuple[Optional[float], Optional[float]], 
    pos2: Tuple[Optional[float], Optional[float]], 
    duration: float = 0.3, 
    steps: int = 5, 
    loops: int = 1
) -> None:
    """
    Move between two pan/tilt poses and return to the starting pose. Pass None for an axis to maintain its starting value.
    
    Examples:
        expressive_gaze((None, 30), (None, -30), loops=4) # Enthusiastic Nod Yes
        expressive_gaze((30, None), (-30, None), duration=1.0, steps=10, loops=2) # Sad Shake No
        expressive_gaze((25, -45), (None, None), duration=0.2, steps=3, loops=3) # Surprised Triple-take
    """
    # 1. Save the current pose
    start_pan, start_tilt = logos.pantilt.get_angles()
    
    # 2. Resolve missing axes to the starting pose
    p1_pan = pos1[0] if pos1[0] is not None else start_pan
    p1_tilt = pos1[1] if pos1[1] is not None else start_tilt
    p2_pan = pos2[0] if pos2[0] is not None else start_pan
    p2_tilt = pos2[1] if pos2[1] is not None else start_tilt
    
    print(f"Performing expressive_gaze between ({p1_pan:.1f}, {p1_tilt:.1f}) and ({p2_pan:.1f}, {p2_tilt:.1f}) for {loops} loop(s)... 👀")
    
    # 3. Execute the moves silently so we don't spam the context window
    with verbosity(Verbosity.SILENT):
        for _ in range(loops):
            logos.core.check_for_interrupt()
            
            logos.pantilt.move(p1_pan, p1_tilt, duration=duration, steps=steps)
            time.sleep(duration * 1.25)
            
            logos.pantilt.move(p2_pan, p2_tilt, duration=duration, steps=steps)
            time.sleep(duration * 1.25)
            
        # 4. Always return to initial pose!
        logos.pantilt.move(start_pan, start_tilt, duration=duration, steps=steps)

def attentive_speech(
    text: str,
    target: str = 'person',
    drive: bool = False,
    align_gain: float = 4.5,
    eye_pan_scale: float = 30.0,
    **kwargs
) -> 'logos.emote.SpeakTask':
    """
    Speak emoji-punctuated text while actively tracking a target to maintain physical presence.
    
    This skill acts as an embodied conversational wrapper around `logos.emote.ttp()`. It runs
    a non-blocking tracking loop to rotate my Kobuki base and adjust my pan-tilt head toward the target
    while my voice is active, creating a natural, attentive posture. It also dynamically synchronizes
    my diffuse chest LEDs to match my active eye color.
    
    Args:
        text: The emoji-punctuated string to speak.
        target: The target label to look for (default 'person').
        drive: If True, physically drives to follow the target. If False, only rotates base.
        align_gain: Proportional gain for base alignment rotation (default 4.5).
        eye_pan_scale: Scale factor for base alignment relative to pan (default 30.0).
        **kwargs: Extra parameters passed to the Text-to-Performance engine (e.g., engine, voice).
        
    Returns:
        SpeakTask: The asynchronous speak task handle.
    """
    import time
    import logos
    import skills.tracking
    from logos.core import Verbosity, verbosity

    # Start speaking asynchronously
    speak_task = logos.emote.ttp(text, wait=False, **kwargs)

    # Active tracking and aesthetic synchronization loop
    with verbosity(Verbosity.SILENT):
        while speak_task.is_active():
            # Allow graceful termination
            logos.core.check_for_interrupt()

            # Track the specified target
            skills.tracking.track_step(
                target=target,
                drive=drive,
                align_gain=align_gain,
                eye_pan_scale=eye_pan_scale
            )

            # Match chest LED to active eye color
            face = logos.emote.get_face_state()
            if face:
                eye_color = face.get("left_eye", {}).get("color")
                if eye_color:
                    logos.leds.fill(eye_color)

            time.sleep(0.05)

    return speak_task
        

def gestural_teleop(timeout: float = 60.0, speed: float = 0.60, turn_speed: float = 30.0) -> None:
    """
    Control my movement using hand gestures detected via the pan-tilt camera.
    
    Gestures:
    - Open Palm: Move Forward
    - Closed Fist: Move Backward
    - Pointing Left: Rotate Left
    - Pointing Right: Rotate Right
    - Two Hands Up: Stop/Exit
    """
    logos.emote.ttp("Visual teleop active! 🖖 Signal me to move, or raise both hands to stop. 🙌", wait=True)
    logos.leds.fill('orange', verbosity=Verbosity.SILENT)
    
    start_time = time.time()
    
    try:
        with logos.verbosity(Verbosity.SILENT):
            while (time.time() - start_time) < timeout:
                logos.core.check_for_interrupt()
                
                # Capture and detect hands
                snap = logos.vision.capture('pan_tilt')
                hands = logos.models.hands(snap.image)
                
                lin_x = 0.0
                ang_z = 0.0
                
                if hands:
                    # Check for stop condition first
                    hands_up = [h for h in hands if h['gesture'] == 'hand_up' and h['confidence'] > 0.6]
                    if len(hands_up) >= 2:
                        print("Stop gesture detected. Exiting teleop.")
                        break
                    
                    # Map gestures to velocities
                    for h in hands:
                        g = h['gesture']
                        if g == 'open_palm': lin_x = speed
                        elif g == 'closed_fist': lin_x = -speed * 0.7
                        elif g == 'pointing_left': ang_z = turn_speed
                        elif g == 'pointing_right': ang_z = -turn_speed
                
                # Apply velocity
                if lin_x != 0 or ang_z != 0:
                    logos.base.velocity(lin_x, ang_z)
                    # Visual feedback: match eye color to movement? 
                    # Let's just keep it simple for now.
                
                time.sleep(0.1) # 10Hz control loop
    finally:
        logos.base.stop()
        logos.leds.fill('off', verbosity=Verbosity.SILENT)
        logos.sound.chime('success')
        logos.emote.ttp("Teleop complete. Stopping here! 🛑", wait=False)



def face_state_visualizer(duration: float = 12.0, rate_hz: float = 15.0) -> None:
    """
    Dynamically drive the notification and pan-tilt LED strips based on my live ASCII face state!
    Maps gaze direction to LED positioning, and mouth amplitude (speech) to LED pulsing/spreading.
    
    Args:
        duration: How long to run the visualizer in seconds.
        rate_hz: Frequency of updates (max ~16Hz supported by face state updates).
    """
    import time
    from logos.core import Verbosity
    
    print("Initializing LED Face-State Visualizer... 🌈👁️")
    start_time = time.time()
    
    num_notif_leds = 16
    
    try:
        with logos.verbosity(Verbosity.SILENT):
            while (time.time() - start_time) < duration:
                logos.core.check_for_interrupt()
                
                face = logos.emote.get_face_state()
                if not face:
                    time.sleep(1.0 / rate_hz)
                    continue
                    
                # Extract colors with defaults
                left_color = face.get("left_eye", {}).get("color", "#00FFFF")
                right_color = face.get("right_eye", {}).get("color", "#FF00FF")
                mouth_color = face.get("mouth", {}).get("color", "#FFFF00")
                
                # Extract gaze and mouth metrics
                gaze_x = face.get("left_eye", {}).get("gaze_x", 0.0) # -1 (right) to 1 (left) from robot perspective
                mouth_amp = face.get("mouth", {}).get("amplitude", 0.0) # 0 to 1
                
                # Map gaze_x (-1.0 to 1.0) to a center index on the notification strip (0 to 15)
                # Left gaze lights up left side, right gaze lights up right side.
                center_idx = int(8 + (gaze_x * 7))
                center_idx = max(0, min(num_notif_leds - 1, center_idx))
                
                # Mouth speaking spreads the light wider!
                spread = max(1, int(mouth_amp * 8))
                
                # Build the notification pattern
                notif_colors = ["off"] * num_notif_leds
                for i in range(num_notif_leds):
                    dist = abs(i - center_idx)
                    if dist <= spread:
                        # Left side gets left eye color, right side gets right eye color
                        if i < 8:
                            notif_colors[i] = left_color
                        else:
                            notif_colors[i] = right_color
                            
                # Update notification strip
                logos.leds.set(notif_colors, strip='notification')

                time.sleep(1.0 / rate_hz)
                
    finally:
        # Revert to safe defaults on completion
        logos.leds.fill('off', strip='notification', verbosity=Verbosity.SILENT)

