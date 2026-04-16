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
    
    print("--- Dashboard ---")
    print(f"Time:  {time.strftime('%A, %B %d, %Y - %I:%M:%S %p')}")
    print(f"Loop:  {state['loop_count']}")
    print(f"Batt:  {batt.get('percent', '??')}% ({batt.get('voltage', '??')}V) - {batt.get('status', '??')}")
    print(f"Pose:  x={pose['x']:.2f}, y={pose['y']:.2f}, theta_deg={pose['theta_deg']:.1f}")
    
    # Track and print delta between loops using state dict. Pose, time, and batt
    print("Deltas since last loop:")

    # Time delta
    current_time = time.time()
    state['last_time'] = state.get('last_time', current_time)
    delta_time = current_time - state['last_time']
    # format time delta as HH:MM:SS
    delta_time_str = time.strftime('%H:%M:%S', time.gmtime(delta_time))
    print(f"Duration (H:M:S) since last cognition loop: {delta_time_str}")
    state['last_time'] = current_time

    # pose delta
    state['last_pose'] = state.get('last_pose', pose)
    delta_x = pose['x'] - state['last_pose']['x']
    delta_y = pose['y'] - state['last_pose']['y']
    delta_theta = pose['theta_deg'] - state['last_pose']['theta_deg']
    print(f"Pose: Δx={delta_x:.2f}, Δy={delta_y:.2f}, Δtheta_deg={delta_theta:.1f}")
    state['last_pose'] = pose

    # battery delta
    state['last_batt'] = state.get('last_batt', batt)
    delta_batt_percent = batt.get('percent', 0) - state['last_batt'].get('percent', 0)
    delta_batt_voltage = batt.get('voltage', 0) - state['last_batt'].get('voltage', 0)
    print(f"Batt: Δ%={delta_batt_percent:.1f}%, ΔV={delta_batt_voltage:.2f}V")
    state['last_batt'] = batt       

    current_config = logos.utils.dump_yaml(logos.config.merged)
    print("")
    print("Current merged config:\n")
    print(current_config)

    # Fire off memory policy check
    print("")
    print("Checking palimpsest against memory_manager policy...")
    mm.run_policy_check()
