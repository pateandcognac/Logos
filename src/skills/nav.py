# Logos/src/skills/nav.py

"""
High-level navigation and spatial planning behaviors. 🗺️

While `logos.nav` provides the core primitives for moving the physical base, 
this module contains my "userland" skills for complex travel logic. These skills 
bridge the gap between visual perception, spatial reasoning (Map3d), and 
obstacle avoidance. They handle graceful fallbacks, journey monitoring, 
and integrating interactive behaviors into otherwise mundane travel time.
"""

import time
import logos
from logos.vision import CaptureResult
from typing import List, Dict, Any, Union, Callable, Optional
import time
import logos
from logos.map3d import RenderResult
from logos.vision import CaptureResult

def find_reachable_goal(
    scene_result: Union[RenderResult, CaptureResult], 
    trajectory: List[Dict[str, Any]]
) -> Union[logos.nav.NavTask, None]:
    """
    Evaluates a trajectory of points in reverse, finding the furthest reachable goal.
    
    Accepts either a map3d RenderResult or an astra CaptureResult.
    Does NOT follow the path as waypoints; simply treats the list as prioritized 
    destinations (last in list = most desired goal).

    Args:
        scene_result: The Map3d render OR Astra capture the points are based on.
        trajectory: A list of dicts containing normalized [y, x] "point" coordinates.
                    e.g. [{"point": [200, 300], "label": "waypoint_1"}, ...]
    """
    for pt in reversed(trajectory):
        target_yx = pt.get("point")
        label = pt.get("label", "unnamed_point")
        if not target_yx: continue

        # 1. Project the pixel to 3D based on the source type
        world_pt = None
        if isinstance(scene_result, RenderResult):
            hit = logos.map3d.raycast(scene_result, target_yx)
            if hit.hit == "floor":
                world_pt = hit.point
        elif isinstance(scene_result, CaptureResult) and scene_result.source == "astra":
            world_pt = scene_result.derive_world_coordinate(target_yx)
        
        # 2. Try the point
        if world_pt:
            task = logos.nav.go_to_abs(world_pt[0], world_pt[1], wait=False)
            time.sleep(0.5) # Let ROS Nav stack build a costmap plan
            
            if task.status() not in ['ABORTED', 'REJECTED', 'LOST']:
                print(f"Goal accepted for '{label}' at x:{world_pt[0]:.2f}, y:{world_pt[1]:.2f}")
                return task
            else:
                print(f"Goal rejected for '{label}' (Status: {task.status()}). Falling back...")
                task.cancel()
        else:
            print(f"Could not derive valid 3D coordinate for '{label}'. Falling back...")

    print("All points in trajectory failed or were unreachable.")
    return None


def monitor_journey(
    nav_task: logos.nav.NavTask,
    callback: Optional[Callable[[CaptureResult, float], None]] = None,
    time_interval_sec: float = 10.0
) -> bool:
    """
    Actively monitors a running NavTask, captures quad-composite photos at 20/40/60/80%
    progress, and executes an optional callback function periodically.

    Args:
        nav_task: The active NavTask to monitor.
        callback: An optional function `my_func(image: CaptureResult, progress: float)`
                  executed on time intervals AND image intervals.
        time_interval_sec: Minimum seconds between time-based callback triggers.

    Returns:
        True if the navigation succeeded, False otherwise.
    """
    # We want photos at exactly these progress thresholds
    photo_thresholds = [0.2, 0.4, 0.6, 0.8]
    breadcrumbs = []
    
    last_callback_time = time.time()
    
    # Reset pan/tilt so we are looking forward while driving
    logos.pantilt.home()

    while nav_task.is_active():
        logos.core.check_for_interrupt()
        prog = nav_task.progress()
        now = time.time()
        
        trigger_photo = False
        trigger_callback = False
        
        # 1. Check if we crossed a progress threshold for a photo
        if photo_thresholds and prog >= photo_thresholds[0]:
            photo_thresholds.pop(0) # Remove threshold so it doesn't trigger again
            trigger_photo = True
            trigger_callback = True # Always callback when taking a progress photo
            
        # 2. Check if enough time has passed for a standard callback
        if now - last_callback_time >= time_interval_sec:
            trigger_callback = True
            
        # Execute triggers
        if trigger_callback:
            # Captures are cheap. Take one to pass to the callback.
            snap = logos.vision.capture('pan_tilt', save=False, view=False)
            if snap:
                if trigger_photo and len(breadcrumbs) < 4:
                    # Keep a reference for the final quad_composite
                    pose = logos.ros.get_pose()
                    snap.add_meta(prog=f"{prog*100:.0f}%", pose=f"x:{pose['x']:.1f}, y:{pose['y']:.1f}")
                    breadcrumbs.append(snap)
                    
                if callback:
                    try:
                        callback(snap, prog)
                    except Exception as e:
                        print(f"Callback error at {prog*100:.0f}%: {e}")
                        
            last_callback_time = now
            
        time.sleep(0.2) # Yield CPU
        
    # Journey ended. Stitch the quad composite!
    if breadcrumbs:
        quad = logos.vision.make_quad_composite(breadcrumbs, target_res=(960, 1280))
        quad.save()
        # Put the travel log on the workbench for 2 loops
        logos.hooks.state.setdefault('workbench', {})
        workbench_code = f"print('<file path=\"{quad.path}\">Travel Log</file>')"
        import hook_routines.workbench as wb
        wb.upsert("journey_review", workbench_code, ltl=2)
        print("Travel log quad-composite added to Context Workbench.")

    return nav_task.succeeded()