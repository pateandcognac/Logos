<py>
"""
Proprioception Sweep Hook Routine
---------------------------------
Performs a quick 360-ish degree visual check of the immediate surroundings.
Captures a Top-Down rear view and a 3-part Pan-Tilt floor sweep.
Stitches them into a Quad Composite with grounding geometry metadata.
"""

# todo: add gating based on time and pose
# only run every 30 minutes or if those pose has changed laterally more than 15cm, or theta +/- 20  degrees
# this will cut down on latency and increase chances of caching.
# also print some info like
# gated capture every 30 min after significant pose change
# last captured x minutes ago at pose (x, y, theta). current pose, and delta.



import time
import logos
from logos.core import verbosity, Verbosity

def run():
    # Use silent verbosity to avoid polluting the context with motor/capture logs
    with verbosity(Verbosity.SILENT):
        
        # 1. Capture Top-Down (Proprioception/Rear)
        # ----------------------------------------------------------------
        # This camera is at (-0.15, 0, 1.0) looking at (0, 0, 0)
        snap_top = logos.vision.capture('top_down', save=False, view=False)
        
        if snap_top:
            # We add specific grounding info. 
            # This helps the LLM map this view to the map3d API arguments.
            snap_top.add_meta(camera_pos_relative="[-0.15, 0, 1.0]")
            # snap_top.add_meta(look_at_relative="(0, 0, 0)")


        # 2. Capture Pan-Tilt Sweep (Frontal 180-ish)
        # ----------------------------------------------------------------
        # Save start pos to restore later
        start_pan, start_tilt = logos.pantilt.get_position()
        
        # Define sweep: (Pan, Tilt, Semantic Label)
        # Note: -70 is Left, 0 is Center, 60 is Right
        sweep_config = [
            (-70, -60, "Floor Left"),
            (0, -60,   "Floor Center"),
            (60, -60,  "Floor Right")
        ]
        
        pan_tilt_snaps = []
        # The fixed position of the pan/tilt base mechanism
        

        for pan, tilt, label in sweep_config:
            # Move quickly but smoothly
            logos.pantilt.move(pan, tilt, steps=10, duration=0.4)
            # Brief pause to let physical vibrations settle for a crisp shot
            time.sleep(0.2) 
            
            res = logos.vision.capture('pan_tilt', save=False, view=False)
            if res:
                # Inject grounding info: specific angles + camera base position
                res.add_meta(
                    label_override=label, # Helper for our label logic below
                    camera_pos_relative="[0, 0.10, 1.10]",
                    pan=f"{pan:.1f}",
                    tilt=f"{tilt:.1f}",
                )
                
                # We REMOVE 'pose' from these frames. 
                # We only want the robot's global map pose displayed once (on the top-down view).
                if 'pose' in res.meta:
                    del res.meta['pose']
                    
                pan_tilt_snaps.append(res)

        # Restore head position to where it was
        logos.pantilt.move(start_pan, start_tilt, steps=5, duration=0.2)

    # 3. Stitch and Display
    # ----------------------------------------------------------------
    if snap_top and len(pan_tilt_snaps) == 3:
        items = [snap_top] + pan_tilt_snaps
        
        # Construct custom labels for the quad view
        labels = [
            "Top-Down (Rear)",
            pan_tilt_snaps[0].meta.get('label_override', 'Left'),
            pan_tilt_snaps[1].meta.get('label_override', 'Center'),
            pan_tilt_snaps[2].meta.get('label_override', 'Right')
        ]

        # Create composite
        # We request 'pose' and 'geometry_info'. 
        # Since we deleted 'pose' from the PT snaps, it will only render on the Top-Down quadrant.
        quad_view = logos.vision.make_quad_composite(
            items, 
            labels=labels,
            meta_keys=['pose', 'camera_pos_relative', 'look_at_relative', 'pan', 'tilt' ], 
            target_res=(960, 1280) # Resulting quadrants are 480x640
        )
        
        # This view() call prints the <file> tag to the context
        print("<!-- hook: proprioception_sweep -->")
        quad_view.view()
    else:
        print("<!-- hook: proprioception_sweep failed (camera unavailable) -->")

run()
</py>