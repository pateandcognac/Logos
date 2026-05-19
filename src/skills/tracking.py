# src/skills/tracking.py

"""
Tracking and alignment skills.

These behaviors translate spatial detections into physical motor commands,
allowing me to maintain "eye contact" or follow targets with my base.
"""

from typing import Dict, List, Tuple, Union, Any, Optional
import time
import math
import numpy as np
import logos
from logos.vision import CaptureResult
import logos.utils
from logos.core import Verbosity, verbosity, check_for_interrupt


# Tiny global state to coast through YOLO flicker
_tracking_state = {
    "last_seen_time": 0.0,
    "last_depth": 1.5,
    "last_turn_speed": 0.0,
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
    drive: bool = False,
    target_dist: float = 0.66,
    align_gain: float = 3.0,
    eye_pan_scale: float = 25.0,
    eye_damp: float = 0.05,
    max_turn: float = 35.0,
    look_deadband: float = 120.0,
) -> bool:
    """
    A single non-blocking tick of a composable tracking loop.

    Detects the target in the pan-tilt camera, steers the pan-tilt onto it,
    then uses the resulting pan angle as the base rotation error — the
    further I'm looking sideways, the more I spin my body to re-center.
    When not driving, animatronic eye gaze is coupled into the rotation so
    my body organically follows where my animated eyes wander. When driving,
    Astra depth keeps me at the desired standoff distance.

    Args:
        target: COCO class name to track (e.g. "person").
        drive: If True, moves forward/back to maintain `target_dist`.
               Eye coupling is automatically disabled while driving.
        target_dist: Desired standoff distance in metres (drive=True only).
        align_gain: Base rotation P-gain — deg/s per degree of pan error.
        eye_pan_scale: How many degrees of pan offset a full gaze_x unit
                       produces. This is a true position target, not a speed —
                       e.g. 15.0 means gaze fully right shifts the equilibrium
                       so I'm looking 15° right of the person. The P-controller
                       then drives the base to reach that new equilibrium and stops.
        eye_damp: Derivative gain on odom angular velocity, applied to the
                  eye-coupling term to soften overshoot on fast gaze snaps.
                  Set to 0.0 to disable.
        max_turn: Hard clamp on turn speed in deg/s.
        look_deadband: How far (in 0-1000 image units) the detection center
                       must be from the frame center before look_at() fires.
                       Keeps the pan-tilt servo from hunting when the target
                       is already roughly centered.

    Returns:
        True if the target was seen recently, False if the coast window expired.

    Note to self:
        Drop this in a tight loop with a short sleep (0.05s). The Kobuki watchdog
        will auto-stop the base if my loop hangs for more than ~0.6s, so there is
        no need for an explicit stop on exit — just let the loop end.
    """
    global _tracking_state
    now = time.time()
    drive_speed = 0.0
    turn_speed = 0.0

    # ── 1. Detect on pan-tilt ────────────────────────────────────────────
    pt_res = logos.vision.capture('pan_tilt', verbosity=Verbosity.SILENT)
    pt_dets = []
    if pt_res is not None:
        pt_dets, pt_res = logos.models.yolo11(pt_res, classes=[target])

    if pt_dets:
        _tracking_state["last_seen_time"] = now

        # ── 2. Pan angle IS the base rotation error ──────────────────────
        # Read the pan angle first so we have the pre-look_at reference.
        # After look_at the servo will point at the target — that updated
        # angle is how far the target sits from dead-ahead on my body axis.
        _, cx = logos.utils.get_box_center(pt_dets[0]["box_2d"])
        x_err = abs(cx - 500.0)  # 0-500 range; 500 = half-frame off-center

        # Only move the head when the person is meaningfully off-center.
        # Skipping small corrections prevents the servo from hunting/oscillating
        # while the base is already rotating to catch up.
        if x_err > look_deadband:
            look_at(pt_dets[0], capture_result=pt_res, duration=0.1, steps=3)

        pan_deg, _ = logos.pantilt.get_angles()

        # ── 3. Compute pan error with optional eye-coupling offset ───────
        # Without eye coupling: drive pan toward 0 (target dead-ahead).
        # With eye coupling: shift the target pan by gaze — the body settles
        # at a new equilibrium where I'm looking eye_pan_scale degrees to the
        # side of the target. The P-controller provides velocity naturally, so
        # this is a true position target rather than a raw speed addition.
        # gaze_x > 0 = eyes drift right → want pan negative (looking right)
        if not drive:
            face = logos.emote.get_face_state()
            gaze_x = face.get("left_eye", {}).get("gaze_x", 0.0) if face else 0.0
            target_pan = -gaze_x * eye_pan_scale
        else:
            target_pan = 0.0

        pan_error = pan_deg - target_pan
        if abs(pan_error) >= 1.0:
            turn_speed = pan_error * align_gain
            if eye_damp > 0.0 and not drive:
                turn_speed -= eye_damp * logos.base.get_odom()["angular_z_deg"]

        # ── 4. Drive: Astra depth sampling ──────────────────────────────
        if drive:
            astra_res = logos.vision.capture('astra', verbosity=Verbosity.SILENT)
            if astra_res is not None:
                astra_dets, astra_res = logos.models.yolo11(astra_res, classes=[target])
                if astra_dets and astra_res.depth_points is not None:
                    box = astra_dets[0]["box_2d"]
                    cy, cx = logos.utils.get_box_center(box)
                    H, W = astra_res.depth_points.shape[:2]
                    py = int(max(0, min(H - 1, cy / 1000.0 * H)))
                    px = int(max(0, min(W - 1, cx / 1000.0 * W)))
                    # Sample a patch around detection center; filter out invalid zeros
                    r = 5
                    patch_z = astra_res.depth_points[
                        max(0, py - r):py + r + 1,
                        max(0, px - r):px + r + 1,
                        2
                    ]
                    valid = patch_z[patch_z > 0.1]
                    if len(valid) > 0:
                        depth_m = float(np.median(valid))
                        _tracking_state["last_depth"] = depth_m
                        dist_error = depth_m - target_dist
                        if abs(dist_error) >= 0.015:
                            # drive_speed = max(-0.18, min(0.28, dist_error * 1.0))
                            drive_speed = max(-0.28, min(0.4, dist_error * 1.0))

        time.sleep(0.1)


    else:
        # ── 5. Lost-target handling ──────────────────────────────────────
        elapsed = now - _tracking_state["last_seen_time"]
        if elapsed > 2.5:
            # Coast window expired — signal the loop to stop
            logos.base.velocity(
                linear_x=0.0, angular_z_deg=0.0, topic="muxed",
                verbosity=logos.Verbosity.SILENT
            )
            return False
        # Still within the coast window: decay the last known turn so we
        # keep rotating gently in the direction we last saw the target
        turn_speed = _tracking_state["last_turn_speed"] * 1.8

    # ── 6. Clamp, cache, and publish ─────────────────────────────────────
    turn_speed = max(-max_turn, min(max_turn, turn_speed))
    _tracking_state["last_turn_speed"] = turn_speed

    logos.base.velocity(
        linear_x=drive_speed,
        angular_z_deg=turn_speed,
        topic="muxed",
        verbosity=logos.Verbosity.SILENT,
    )
    return True
