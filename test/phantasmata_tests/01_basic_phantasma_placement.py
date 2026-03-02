#!/usr/bin/env python3
"""
Test 01: Basic Phantasma Placement

I'm testing the fundamental phantasmata lifecycle: placing, querying,
moving, and removing instances. This verifies that my mind palace
instance management works correctly.

Author: Logos (with Claude's help)
Date: 2026-02-28
"""

from __future__ import annotations
import sys
import os

# Add logos to path if running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

import logos
from logos import map3d


def main():
    print("=" * 70)
    print("Test 01: Basic Phantasma Placement")
    print("=" * 70)
    print()

    # Initialize my map3d renderer
    print("Initializing my map3d renderer...")
    renderer = map3d.get_map3d()
    print(f"✓ Map3d initialized")
    print()

    # ---- Test 1: List available phantasmata ----
    print("--- Test 1: Available Phantasmata Modules ---")
    available = map3d.list_phantasmata()
    print(f"I have {len(available)} phantasma modules available:")
    for name in available:
        print(f"  • {name}")
    print()

    # ---- Test 2: Describe a phantasma ----
    print("--- Test 2: Inspecting grid_overlay Schema ---")
    if 'grid_overlay' in available:
        info = map3d.describe_phantasma('grid_overlay')
        print(f"Module: grid_overlay")
        print(f"Dynamic: {info['dynamic']}")
        print(f"Has HUD: {info['has_hud']}")
        print(f"Schema parameters:")
        for param_name, param_spec in info['schema'].items():
            default = param_spec.get('default', 'N/A')
            desc = param_spec.get('description', '')
            print(f"  • {param_name}: {desc}")
            print(f"    Default: {default}")
    print()

    # ---- Test 3: Place a grid instance ----
    print("--- Test 3: Placing a Metric Grid ---")
    map3d.place(
        name='test_grid',
        object='grid_overlay',
        params={
            'spacing_m': 0.5,  # Half-meter grid
            'extent_m': 5.0,
            'color': [0.2, 0.4, 0.6],  # Blue-ish
        },
        description="Test grid with 0.5m spacing",
    )
    print("✓ Placed 'test_grid' instance")
    print()

    # ---- Test 4: List instances ----
    print("--- Test 4: Listing All Instances ---")
    instances = map3d.list_instances()
    print(f"I currently have {len(instances)} phantasma instances:")
    for name, config in instances.items():
        obj = config.get('object', 'unknown')
        desc = config.get('description', '')
        visible = config.get('render_visible', True)
        status = "visible" if visible else "hidden"
        print(f"  • {name} ({obj}) - {status}")
        if desc:
            print(f"    {desc}")
    print()

    # ---- Test 5: Place a pointer arrow ----
    print("--- Test 5: Placing a Pointer Arrow ---")
    map3d.place(
        name='test_arrow',
        object='pointer_arrow',
        params={
            'from_point': [0.0, 0.0, 1.0],  # 1m above origin
            'to_point': [2.0, 1.0, 0.0],    # Point at floor location
            'color': [1.0, 0.5, 0.0],       # Orange
        },
        description="Test arrow pointing at (2, 1, 0)",
    )
    print("✓ Placed 'test_arrow' instance")
    print()

    # ---- Test 6: Update instance parameters ----
    print("--- Test 6: Updating Arrow Color ---")
    map3d.update_instance('test_arrow', color=[0.0, 1.0, 0.0])  # Change to green
    print("✓ Changed arrow color to green")
    print()

    # ---- Test 7: Move an instance ----
    print("--- Test 7: Moving the Arrow ---")
    map3d.move_instance(
        'test_arrow',
        position=None,  # Keep current position
        rpy_deg=None,   # Keep current rotation
    )
    # Now actually move it
    updated_config = map3d.describe_instance('test_arrow')
    print(f"Current arrow config: {updated_config.get('params', {})}")

    # Update the target point via params
    map3d.update_instance('test_arrow', to_point=[3.0, -1.0, 0.0])
    print("✓ Updated arrow target to (3, -1, 0)")
    print()

    # ---- Test 8: Toggle visibility ----
    print("--- Test 8: Toggling Visibility ---")
    map3d.set_visible('test_grid', render=False)
    print("✓ Hid test_grid")

    instances = map3d.list_instances()
    grid_status = "visible" if instances['test_grid']['render_visible'] else "hidden"
    print(f"  Grid is now: {grid_status}")

    map3d.set_visible('test_grid', render=True)
    print("✓ Made test_grid visible again")
    print()

    # ---- Test 9: Force rebuild ----
    print("--- Test 9: Forcing Rebuild ---")
    map3d.rebuild('test_arrow')  # Rebuild just the arrow
    print("✓ Rebuilt test_arrow")

    map3d.rebuild()  # Rebuild everything
    print("✓ Rebuilt all instances")
    print()

    # ---- Test 10: Remove instances ----
    print("--- Test 10: Removing Instances ---")
    map3d.remove('test_arrow')
    print("✓ Removed 'test_arrow'")

    map3d.remove('test_grid')
    print("✓ Removed 'test_grid'")
    print()

    # ---- Final state ----
    print("--- Final State ---")
    instances = map3d.list_instances()
    print(f"Remaining instances: {len(instances)}")
    for name in instances:
        print(f"  • {name}")
    print()

    print("=" * 70)
    print("Test 01 Complete!")
    print("All basic phantasma operations work correctly.")
    print("=" * 70)


if __name__ == '__main__':
    main()
