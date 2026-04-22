# src/hook_routines/vision.py

import logos
from logos.core import Verbosity, verbosity

def run():
    """
    Executes the primary vision hook. Reads config, captures enabled cameras,
    applies overlays, publishes to ROS, and returns the results.
    """
    # Read the configuration
    config = logos.config.merged.get('vision_hook', {})
    
    results = {}
    cameras = ['pan_tilt', 'astra', 'top_down']
    captured_any = False
    
    # Silence the individual API capture ACKs to keep the context window tidy
    with verbosity(Verbosity.SILENT):
        for cam in cameras:
            cam_cfg = config.get(cam, {})
            if not cam_cfg.get('enabled', False):
                continue
                
            # Parse parameters
            res_list = cam_cfg.get('resolution')
            resolution = tuple(res_list) if res_list else logos.vision.DEFAULT_RESOLUTION.get(cam, (480, 640))
            meta_keys = cam_cfg.get('meta_keys', [])
            
            # Special handling for Astra feeds
            feeds = tuple(cam_cfg.get('feeds', logos.vision.DEFAULT_ASTRA_FEEDS)) if cam == 'astra' else None
            
            # Perform the capture (save=True to write the file, view=False until we apply overlays)
            if cam == 'astra':
                res = logos.vision.capture(source=cam, resolution=resolution, astra_feeds=feeds, save=True, view=False)
            else:
                res = logos.vision.capture(source=cam, resolution=resolution, save=True, view=False)
                
            if res:
                # 1. Apply Astra grid overlay if configured
                if cam == 'astra' and cam_cfg.get('overlay_grid', {}).get('enabled', False):
                    grid_cfg = cam_cfg['overlay_grid']
                    res.overlay_coordinate_grid(rows=grid_cfg.get('rows', 3), cols=grid_cfg.get('cols', 4))
                    # Save again to overwrite the artifact on disk with the burned-in grid
                    res.save(view=False)
                    
                # 2. Publish to ROS debug topic (so Mark can see my raw/gridded feed!)
                # logos.vision.publish_debug(res.image, detections=None, source=cam)
                
                # 3. Print the <file> tag for my context window
                res.view(meta_keys=meta_keys)
                
                results[cam] = res
                captured_any = True
                print(f"Image CaptureResult available as {cam}_result.  {res.resolution[0]}x{res.resolution[1]}.")
            else:
                print(f"{cam}_result Failed to capture!")

    # Context window instructions
    if captured_any:
        print("Variables are available in memory for `<py>` blocks.")
        print("Examples: `pan_tilt_result.crop(...)`, `astra_result.derive_world_coordinate(...)`")
        # if astra and overlay enabled, mention the grid overlay
        if 'astra' in results and config.get('vision_hook', {}).get('astra', {}).get('overlay_grid', {}).get('enabled', False):
            print("Astra grid_overlay is enabled, showing the derived 3D coordinates of pixels in (C)amera and (M)ap frames. Disable for clearer view.")
    else:
        print("No cameras enabled. (Toggle via `logos.config.prefs.vision_hook`)")
            
    return results