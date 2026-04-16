# Logos/src/skills/tracking.py

"""
Tracking and alignment skills.

These behaviors translate spatial detections into physical motor commands, 
allowing me to maintain "eye contact" or follow targets with my base.
"""

from typing import Dict, Any, Optional
import time
import logos
from skills.vision import smart_detect

# A tiny global state to coast through YOLO flicker
_tracking_state = {
    "last_seen_time": 0.0,
    "last_depth": 1.0,
}

def look_at(detection: Dict[str, Any], source: str = "pan_tilt", continuous: bool = False) -> None:
    """
    Aim the pan-tilt head at a detection.
    (Updated to support non-blocking continuous tracking)
    """
    box = detection.get("box_2d")
    if not box: return

    y1, x1, y2, x2 = box
    label = detection.get("label", "").lower()

    target_y = y1 + ((y2 - y1) * 0.15) if label == "person" else (y1 + y2) / 2.0
    target_x = (x1 + x2) / 2.0

    # If tracking continuously, use fast, non-blocking moves
    dur = 0.1 if continuous else 0.4
    steps = 1 if continuous else 10

    if label == "person" and y1 < 50:
        # Target's head is cut off, search up!
        logos.pantilt.nudge(0, 10) 
    else:
        # We manually replicate look_at_pixel here to pass dur/steps
        # Convert to fraction from center
        x_frac = (target_x / 1000.0) - 0.5
        y_frac = (target_y / 1000.0) - 0.5
        fov_h, fov_v = logos.vision.FOV[source]
        
        current_pan, current_tilt = logos.pantilt.get_position()
        # +x_frac (target is right) means we must Pan Right (negative)
        new_pan = current_pan + (-x_frac * fov_h)
        new_tilt = current_tilt + (-y_frac * fov_v)
        
        logos.pantilt.move(
            new_pan, new_tilt, duration=dur, steps=steps, 
            verbosity=logos.Verbosity.SILENT
        )

def track_step(
    target: str = "person",
    drive: bool = True,
    couple_eyes: bool = True,
    target_dist: float = 1.0,
) -> bool:
    """
    A single tick of a highly composable sensor-fusion tracking loop.
    
    Fuses Astra (Source of Truth), Pan-Tilt (Scout), and Eyes (Flavor) into 
    smooth base movements. Also handles Pan-Tilt head tracking automatically.

    Args:
        target: The YOLO/World target to track.
        drive: If True, moves forward/back to maintain `target_dist`.
               If False, only rotates base/head to follow.
        couple_eyes: If True, animatronic gaze influences base rotation.
        target_dist: Desired distance in meters.

    Returns:
        True if the target was seen recently, False if completely lost.
    """
    global _tracking_state
    now = time.time()
    
    # 1. Grab both cameras (warm up first if needed, but in a loop they stay warm)
    pt_img = logos.vision.capture('pan_tilt').image
    astra_res = logos.vision.capture('astra')
    
    # 2. Track with Head (Pan-Tilt)
    pt_dets = smart_detect(pt_img, target)
    if pt_dets:
        look_at(pt_dets[0], source="pan_tilt", continuous=True)
    
    # 3. Track with Base (Astra + Head Fusion)
    astra_dets = smart_detect(astra_res.image, target)
    target_heading_deg = 0.0
    drive_speed = 0.0
    turn_speed = 0.0
    
    if astra_dets:
        _tracking_state["last_seen_time"] = now
        
        # --- ROTATION CALCULATION ---
        # Astra is source of truth. Map pixel error to degrees.
        box = astra_dets[0]["box_2d"]
        center_x = (box[1] + box[3]) / 2.0
        # Positive error = target is to the LEFT.
        error_frac = 0.5 - (center_x / 1000.0) 
        astra_fov_h = logos.vision.FOV["astra_rgb"][0]
        target_heading_deg = error_frac * astra_fov_h
        
        # --- DRIVE CALCULATION ---
        if drive and astra_res.depth_points is not None:
            # derive_world_coordinate averages out NaN pixels!
            world_pt = astra_res.derive_world_coordinate(box)
            if world_pt:
                # Calculate hypotenuse distance (ignoring Z height)
                import math
                dist = math.hypot(world_pt[0], world_pt[1])
                _tracking_state["last_depth"] = dist
                
                # Proportional drive control
                dist_error = dist - target_dist
                drive_speed = dist_error * 0.4 # Kp_drive
                # Clamp speed
                drive_speed = max(-0.2, min(0.3, drive_speed))
                
                # If they are super close (depth NaN usually <0.4m), world_pt might fail. 
                # We handle that below.

    else:
        # Astra lost them. Are they around the corner? Let's check the head!
        current_pan, _ = logos.pantilt.get_position()
        
        if abs(current_pan) > 15.0:
            # The head is looking away from center. Assume it's tracking the target.
            # Base needs to turn to catch up to the head.
            target_heading_deg = current_pan
            
        # Coasting logic for drive
        if now - _tracking_state["last_seen_time"] < 1.0:
            # Coast using last known depth
            dist_error = _tracking_state["last_depth"] - target_dist
            drive_speed = (dist_error * 0.4) * 0.5 # Halved speed while coasting
        else:
            # Target completely lost
            return False

    # 4. Add Eye Coupling "Flavor"
    if couple_eyes:
        face_state = logos.emote.get_face_state()
        if face_state:
            gaze_x = face_state.get("left_eye", {}).get("gaze_x", 0.0)
            # If eyes dart left (-1.0), add ~10 degrees to target heading
            target_heading_deg += (-gaze_x * 10.0)

    # 5. Execute Base Movement
    # Kp_turn converts heading degrees to turn speed
    turn_speed = target_heading_deg * 0.03
    turn_speed = max(-40.0, min(40.0, turn_speed)) # Clamp max turn

    # Publish single velocity command (Kobuki watchdog will stop us if loop hangs)
    logos.base.velocity(
        linear_x=drive_speed, 
        angular_z_deg=turn_speed, 
        topic="raw",
        verbosity=logos.Verbosity.SILENT
    )
    
    return True