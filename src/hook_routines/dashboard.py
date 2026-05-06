# src/hook_routines/dashboard.py

import time
import os
from typing import Dict, Any, List, Optional
import logos
import hook_routines.memory_manager as mm


def _format_time_delta(seconds: float) -> str:
    """Converts a duration in seconds to a human-readable string (e.g., '1m 15s')."""
    seconds = int(seconds)
    if seconds < 0:
        return "0s"
    
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    if seconds > 0 or not parts:
        parts.append(f"{seconds}s")
        
    return " ".join(parts)

def _get_python_memory_mb() -> float:
    """
    Gets the current Resident Set Size (RSS) of this specific Python process.
    Crucial for Logos to monitor its own long-running, stateful memory footprint.
    """
    try:
        with open('/proc/self/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    # VmRSS is in kB, convert to MB
                    return int(line.split()[1]) / 1024.0
    except Exception:
        pass
    return 0.0

def run():
    """
    My core cognitive dashboard hook. Provides real-time metrics about my 
    physical state, position, Python environment memory, and hardware health.
    """
    # --- 1. Gather Data ---
    pose: Dict[str, Any] = logos.ros.get_pose() or {'x': 0.0, 'y': 0.0, 'theta_deg': 0.0}
    batt: Dict[str, Any] = logos.base.get_battery() or {}
    current_time: float = time.time()
    current_mem_mb: float = _get_python_memory_mb()
    alerts: Optional[List[Dict[str, Any]]] = logos.ros.get_diagnostic_alerts()
    
    # --- 2. Manage Persistent State & Calculate Deltas ---
    state: Dict[str, Any] = logos.hooks.state.setdefault('dashboard', {
        'loop_count': 0,
        'last_time': current_time,
        'last_pose': pose,
        'last_batt': batt,
        'last_mem_mb': current_mem_mb
    })
    
    state['loop_count'] += 1
    
    delta_time: float = current_time - state['last_time']
    delta_x: float = pose['x'] - state['last_pose']['x']
    delta_y: float = pose['y'] - state['last_pose']['y']
    delta_theta: float = pose['theta_deg'] - state['last_pose']['theta_deg']
    
    delta_batt_percent: float = batt.get('percent', 0.0) - state['last_batt'].get('percent', 0.0)
    delta_batt_voltage: float = batt.get('voltage', 0.0) - state['last_batt'].get('voltage', 0.0)
    
    delta_mem_mb: float = current_mem_mb - state['last_mem_mb']

    # --- 3. Print Formatted Dashboard ---
    print("--- Dashboard ---")
    print(f"Time:       {time.strftime('%A, %B %d, %Y - %I:%M:%S %p')}")
    print(f"Cycle Count:  {state['loop_count']} | Time Since Last: {_format_time_delta(delta_time)}")
    print("")

    if state['loop_count'] < 4:
        print("NOTE: My environment uses lazy subscribers, so my first few loops may contain timeouts or unpopulated fields.\nDon't fret and have patience while topics initialize.\n")

    # Physical State
    print(f"Pose (x, y, θ°):  {pose['x']:>6.2f}m, {pose['y']:>6.2f}m, {pose['theta_deg']:>6.1f}°")
    print(f"    Δ (x, y, θ°): {delta_x:>+6.2f}m, {delta_y:>+6.2f}m, {delta_theta:>+6.1f}°")
    print(f"Battery:          {batt.get('percent', '??'):>6.1f}% ({batt.get('voltage', '??'):.2f}V) - {batt.get('status', 'Unknown')}")
    print(f"    Δ (%, V):     {delta_batt_percent:>+6.1f}% ({delta_batt_voltage:+.2f}V)")
    
    # --- 4. Diagnostics Module ---
    print("")
    if alerts is None:
        print("Diagnostics: [Awaiting Data...]")
    elif len(alerts) == 0:
        print("Diagnostics: [All Systems Nominal! 👍]")
    else:
        print("Diagnostics: [Alert! ⚠️]")
        # Limit to first 3 alerts to prevent massive context bloat if something fails cascadingly
        for alert in alerts[:3]: 
            print(f"  [{alert['level_str']}] {alert['name']}")
            print(f"     Msg: {alert['message']}")
            # Only print values if there's space, and cap it to the first few to keep it sane
            val_strs = [f"{k}={v}" for k, v in list(alert['values'].items())[:4]]
            if val_strs:
                print(f"     Vals: {', '.join(val_strs)}")
        
        if len(alerts) > 3:
            print(f"  ... and {len(alerts) - 3} more alert(s).")

    # Python Memory
    print(f"\nPython Env Memory: {current_mem_mb:>6.1f} MB (Δ {delta_mem_mb:>+6.1f} MB)")
    print("")

    # --- 5. Update State ---
    state['last_time'] = current_time
    state['last_pose'] = pose
    state['last_batt'] = batt
    state['last_mem_mb'] = current_mem_mb

    # Fire off memory policy check
    print("\nChecking palimpsest against memory_manager policy...")
    mm.run_policy_check()
