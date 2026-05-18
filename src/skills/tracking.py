# src/skills/tracking.py

"""
Tracking and alignment skills.

These behaviors translate spatial detections into physical motor commands, 
allowing me to maintain "eye contact" or follow targets with my base.
"""

from typing import Dict, List, Tuple, Union, Any, Optional
import time
import math
import logos
from skills.vision import smart_detect
from logos.vision import CaptureResult
import logos.utils

# A tiny global state to coast through YOLO flicker
_tracking_state = {
    "last_seen_time": 0.0,
    "last_depth": 1.0,
}

def look_at(
    target: Union[Dict[str, Any], List[Dict[str, Any]], List[float], Tuple[float, float]], 
    capture_result: Optional[CaptureResult] = None, 
    duration: float = 0.25, 
    steps: int = 5
) -> None:
    """
    Aim the pan-tilt head at a detection, bounding box, or point.
    
    If a capture_result is provided, uses its saved metadata to calculate 
    the offset perfectly, compensating for any hardware movement that 
    occurred during image processing.

    Args:
        target: A detection dict, list of dicts, a [y, x] point, or [y1, x1, y2, x2] box.
        capture_result: The CaptureResult this target came from (highly recommended).
        duration: Total time for the movement in seconds. Use 0.0 for instant non-blocking ticks.
        steps: Number of interpolation steps. Use 1 for instant non-blocking ticks.
    """
    # 1. Resolve Target robustly
    resolved_point = logos.utils.resolve_gaze_point(target)
    if not resolved_point:
        print("look_at: Could not resolve target into a [y, x] point. Skipping.")
        return
        
    target_y, target_x = resolved_point

    # 2. Convert 0-1000 pixel coordinates to fraction from center (-0.5 to 0.5)
    x_frac = (target_x / 1000.0) - 0.5
    y_frac = (target_y / 1000.0) - 0.5

    # Always use the pan_tilt camera's FOV for these calculations
    fov_h, fov_v = logos.vision.FOV["pan_tilt"]
    
    # 3. Angular offset: how far from image center in degrees
    # Pan:  object right in image (+x_frac) → pan right (negative)
    # Tilt: object above in image (-y_frac) → tilt up (positive)
    pan_offset = -x_frac * fov_h
    tilt_offset = -y_frac * fov_v

    # 4. Determine our reference angles (Latency Compensation)
    ref_pan, ref_tilt = None, None
    
    if capture_result and capture_result.pan_tilt_degs:
        # Use the angles from the exact millisecond the frame was grabbed
        ref_pan, ref_tilt = capture_result.pan_tilt_degs
        
    if ref_pan is None or ref_tilt is None:
        # Fallback to current live angles
        ref_pan, ref_tilt = logos.pantilt.get_angles()

    new_pan = ref_pan + pan_offset
    new_tilt = ref_tilt + tilt_offset

    # 5. Move!
    logos.pantilt.move(
        new_pan, new_tilt, 
        duration=duration, steps=steps, 
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
    This function contains no blocking sleep calls.

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
    
    # 1. Grab both cameras (Capture entire result so we have metadata)
    pt_res = logos.vision.capture('pan_tilt')
    astra_res = logos.vision.capture('astra')
    
    # 2. Track with Head (Pan-Tilt)
    if pt_res and pt_res.image is not None:
        pt_dets = smart_detect(pt_res.image, target)
        if pt_dets:
            # Fast, non-blocking tick using latency compensation!
            look_at(pt_dets[0], capture_result=pt_res, duration=0.0, steps=1)
            
            # Nudge logic if target's top edge is too close to the top of the frame
            y1 = pt_dets[0].get("box_2d", [0, 0, 0, 0])[0]
            if pt_dets[0].get("label") == "person" and y1 < 50:
                logos.pantilt.nudge(0, 3)
    
    # 3. Track with Base (Astra + Head Fusion)
    target_heading_deg = 0.0
    drive_speed = 0.0
    turn_speed = 0.0
    
    if astra_res and astra_res.image is not None:
        astra_dets = smart_detect(astra_res.image, target)
        
        if astra_dets:
            _tracking_state["last_seen_time"] = now
            
            # --- ROTATION CALCULATION ---
            box = astra_dets[0]["box_2d"]
            center_x = (box[1] + box[3]) / 2.0
            error_frac = 0.5 - (center_x / 1000.0) 
            astra_fov_h = logos.vision.FOV["astra_rgb"][0]
            target_heading_deg = error_frac * astra_fov_h
            
            # --- DRIVE CALCULATION ---
            if drive and astra_res.depth_points is not None:
                world_pt = astra_res.derive_world_coordinate(box)
                if world_pt:
                    pose = logos.ros.get_pose()
                    dist = math.hypot(world_pt[0] - pose['x'], world_pt[1] - pose['y'])
                    _tracking_state["last_depth"] = dist
                    
                    dist_error = dist - target_dist
                    drive_speed = dist_error * 0.4 
                    drive_speed = max(-0.2, min(0.3, drive_speed))

        else:
            # Astra lost them. Are they around the corner? Let's check the head!
            current_pan, _ = logos.pantilt.get_angles()
            
            if abs(current_pan) > 15.0:
                target_heading_deg = current_pan
                
            # Coasting logic for drive
            if now - _tracking_state["last_seen_time"] < 1.0:
                dist_error = _tracking_state["last_depth"] - target_dist
                drive_speed = (dist_error * 0.4) * 0.5 
            else:
                return False

    # 4. Add Eye Coupling "Flavor"
    if couple_eyes:
        face_state = logos.emote.get_face_state()
        if face_state:
            gaze_x = face_state.get("left_eye", {}).get("gaze_x", 0.0)
            target_heading_deg += (-gaze_x * 30.0)

    # 5. Execute Base Movement
    turn_speed = target_heading_deg * 0.03
    turn_speed = max(-40.0, min(40.0, turn_speed)) 

    # Publish single velocity command (Kobuki watchdog will stop us if loop hangs)
    logos.base.velocity(
        linear_x=drive_speed, 
        angular_z_deg=turn_speed, 
        topic="raw",
        verbosity=logos.Verbosity.SILENT
    )
    
    return True