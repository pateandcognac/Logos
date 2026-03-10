# src/hook_routines/dashboard.py

import time
import logos
import hook_routines.memory_manager as mm

def run():
    pose = logos.ros.get_pose()
    batt = logos.base.get_battery()
    
    # We could track loop count in hooks.state
    state = logos.hooks.state.setdefault('dashboard', {'loop_count': 0})
    state['loop_count'] += 1
    
    # print("=== LOGOS DASHBOARD ===")
    print(f"Time:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Loop:  {state['loop_count']}")
    print(f"Batt:  {batt.get('percentage', '??')}% ({batt.get('voltage', '??')}V) - {batt.get('status', '??')}")
    if pose:
        print(f"Pose:  x={pose['x']:.2f}, y={pose['y']:.2f}, deg={pose['deg']:.1f}")
    
    current_config = logos.utils.dump_yaml(logos.config.merged)
    print("")
    print("Current merged config:\n")
    print(current_config)

    # Fire off memory policy check
    print("Checking palimpsest against memory policy...")
    mm.run_policy_check()
