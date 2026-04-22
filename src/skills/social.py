# Logos/src/skills/social.py

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