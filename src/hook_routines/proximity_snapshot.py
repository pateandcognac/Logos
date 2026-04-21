# src/hook_routines/proprioception.py

import math
import time
import logos
from logos.core import verbosity, Verbosity

# Configurable thresholds
TIME_THRESH_SEC = 60 * 60  # 60 minutes
DIST_THRESH_M = 0.2        # 20 cm
ANGLE_THRESH_DEG = 30.0    # 30 degrees

def run():
    state = logos.hooks.state.setdefault('proprioception_sweep', {})
    current_time = time.time()
    current_pose = logos.ros.get_pose()

    last_time = state.get('last_time', 0)
    last_pose = state.get('last_pose')
    
    # --- 1. GATING LOGIC ---
    should_run = False
    
    if current_time - last_time > TIME_THRESH_SEC:
        should_run = True
    elif current_pose and last_pose:
        # Compare current pose strictly against the pose AT LAST CAPTURE
        dx = current_pose['x'] - last_pose['x']
        dy = current_pose['y'] - last_pose['y']
        dist = math.hypot(dx, dy)
        
        diff = abs((current_pose['theta_deg'] - last_pose['theta_deg']) % 360)
        angle_diff = diff if diff <= 180 else 360 - diff
        
        if dist > DIST_THRESH_M or angle_diff > ANGLE_THRESH_DEG:
            should_run = True
    elif current_pose and not last_pose:
        should_run = True
    elif not state.get('cached_composite'):
        # Safety fallback if we somehow don't have a cached image
        should_run = True

    # --- 2. CACHE HIT (Preserve the KV Cache!) ---
    if not should_run:
        # Print the exactly identical strings from the last run
        print(state['cached_header'])
        # The CaptureResult object is frozen, so .view() will output identical metadata/tags
        state['cached_composite'].view(meta_keys=['pose', 'camera_pos_relative', 'pan', 'tilt'])
        return

    # --- 3. CACHE MISS (Run the sweep) ---
    with verbosity(Verbosity.SILENT):
        snap_top = logos.vision.capture('top_down', save=False, view=False)
        if snap_top:
            snap_top.add_meta(camera_pos_relative="[-0.15, 0, 1.0]")

        start_pan, start_tilt = logos.pantilt.get_angles()
        
        sweep_config = [
            (70, -60, "Floor Left"),
            (0, -60,   "Floor Center"),
            (-70, -60,  "Floor Right")
        ]
        
        pan_tilt_snaps = []
        for pan, tilt, label in sweep_config:
            logos.pantilt.move(pan, tilt, steps=5, duration=0.4)
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
                    del res.meta['pose'] 
                pan_tilt_snaps.append(res)

        logos.pantilt.move(start_pan, start_tilt, steps=5, duration=0.2)

    # --- 4. STITCH AND SAVE STATE ---
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
        
        # Save to disk so the <file> tag persists safely
        quad_view.save()
        
        # Construct the static header string
        time_str = time.strftime('%I:%M %p', time.localtime(current_time))
        header_lines = [
            "--- Proprioception Sweep ---",
            f"Captured at: {time_str}"
        ]
        if current_pose:
            header_lines.append(f"Pose: x={current_pose['x']:.2f}, y={current_pose['y']:.2f}, deg={current_pose['theta_deg']:.1f}")
        header_lines.append(f"Refreshes every {TIME_THRESH_SEC//60} min, or when pose changes > {DIST_THRESH_M}m / {ANGLE_THRESH_DEG}deg")
        header_str = "\n".join(header_lines)

        # Update persistent state
        state['last_time'] = current_time
        state['last_pose'] = current_pose
        state['cached_header'] = header_str
        state['cached_composite'] = quad_view
        
        # Print for the current loop
        print(header_str)
        quad_view.view(meta_keys=['pose', 'camera_pos_relative', 'pan', 'tilt'])
    else:
        # Fallback if a camera fails
        print("--- Proprioception Sweep ---")
        print("Status: Failed to acquire camera feeds.")

        # sleep for 1.5 sec to allow pan-tilt to stabilize
        time.sleep(1.5)