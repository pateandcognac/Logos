# src/hook_routines/proprioception.py

import math
import time
import logos
from logos.core import verbosity, Verbosity

# Configurable thresholds (could eventually be pulled from logos.config.merged)
TIME_THRESH_SEC = 60 * 60  # 60 minutes
DIST_THRESH_M = 0.2        # 20 cm
ANGLE_THRESH_DEG = 30.0    # 30 degrees

def run():
    # 1. Fetch persistent state and current pose
    state = logos.hooks.state.setdefault('proprioception_sweep', {})
    current_time = time.time()
    current_pose = logos.ros.get_pose() # returns dict: {'x': float, 'y': float, 'deg': float} or None

    last_time = state.get('last_time', 0)
    last_pose = state.get('last_pose')

    # 2. Gating Logic
    should_run = False
    
    # Condition A: Time has expired
    if current_time - last_time > TIME_THRESH_SEC:
        should_run = True
        
    # Condition B: Pose has changed significantly
    elif current_pose and last_pose:
        dx = current_pose['x'] - last_pose['x']
        dy = current_pose['y'] - last_pose['y']
        dist = math.hypot(dx, dy)
        
        # Handle 360-degree wraparound for angle math
        diff = abs((current_pose['deg'] - last_pose['deg']) % 360)
        angle_diff = diff if diff <= 180 else 360 - diff
        
        if dist > DIST_THRESH_M or angle_diff > ANGLE_THRESH_DEG:
            should_run = True
            
    # Condition C: First run with a valid pose
    elif current_pose and not last_pose:
        should_run = True

    # If nothing triggered, exit silently to preserve the context cache!
    if not should_run:
        return

    # 3. Execution
    with verbosity(Verbosity.SILENT):
        snap_top = logos.vision.capture('top_down', save=False, view=False)
        if snap_top:
            snap_top.add_meta(camera_pos_relative="[-0.15, 0, 1.0]")

        start_pan, start_tilt = logos.pantilt.get_position()
        
        sweep_config = [
            (-70, -60, "Floor Left"),
            (0, -60,   "Floor Center"),
            (60, -60,  "Floor Right")
        ]
        
        pan_tilt_snaps = []
        for pan, tilt, label in sweep_config:
            logos.pantilt.move(pan, tilt, steps=10, duration=0.4)
            time.sleep(0.2) 
            
            res = logos.vision.capture('pan_tilt', save=False, view=False)
            if res:
                res.add_meta(
                    label_override=label,
                    camera_pos_relative="[0, 0.10, 1.10]",
                    pan=f"{pan:.1f}",
                    tilt=f"{tilt:.1f}",
                )
                if 'pose' in res.meta:
                    del res.meta['pose'] # Only show global pose on Top-Down
                pan_tilt_snaps.append(res)

        logos.pantilt.move(start_pan, start_tilt, steps=5, duration=0.2)

    # 4. Stitch, Display, and Update State
    if snap_top and len(pan_tilt_snaps) == 3:
        items = [snap_top] + pan_tilt_snaps
        labels = [
            "Top-Down (Rear)",
            pan_tilt_snaps[0].meta.get('label_override', 'Left'),
            pan_tilt_snaps[1].meta.get('label_override', 'Center'),
            pan_tilt_snaps[2].meta.get('label_override', 'Right')
        ]

        quad_view = logos.vision.make_quad_composite(
            items, 
            labels=labels,
            meta_keys=['pose', 'camera_pos_relative', 'pan', 'tilt'], 
            target_res=(960, 1280)
        )
        
        # Update State Variables
        state['last_time'] = current_time
        state['last_pose'] = current_pose
        
        # Print Grounding Header
        time_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(current_time))
        print("--- Proprioception Sweep ---")
        print(f"Captured at: {time_str}")
        if current_pose:
            print(f"Pose: x={current_pose['x']:.2f}, y={current_pose['y']:.2f}, deg={current_pose['deg']:.1f}")
        print(f"Refreshes every {TIME_THRESH_SEC//60} min, or movement > {DIST_THRESH_M}m / {ANGLE_THRESH_DEG}deg")
        
        quad_view.view()