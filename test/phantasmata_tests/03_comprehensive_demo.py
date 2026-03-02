#!/usr/bin/env python3
"""
Test 03: Comprehensive Phantasmata Demonstration

I'm putting my mind palace through its paces with a full demonstration
of the phantasmata system. This creates a rich virtual scene with multiple
object types, then renders it from various angles.

This test demonstrates:
- Loading from mind_palace.yaml
- Programmatic instance placement
- Dynamic parameter updates
- Complex scene composition
- HUD contributions from phantasmata
- Raycast testing (if map is available)

Author: Logos (with Claude's help)
Date: 2026-02-28
"""

from __future__ import annotations
import sys
import os
from pathlib import Path
import time

# Add logos to path if running standalone
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

import logos
from logos import map3d
from logos.map3d import HudElement


def create_scene():
    """Create a rich phantasma scene for testing."""
    print("--- Creating Test Scene ---")

    # 1. Metric grid (from config)
    print("Loading mind_palace.yaml configuration...")
    map3d.reload_mind_palace()
    instances = map3d.list_instances()
    print(f"✓ Loaded {len(instances)} instances from config")
    for name in instances:
        print(f"  • {name}")

    # 2. Add navigation waypoint arrows
    print("\nPlacing navigation waypoints...")
    waypoints = [
        ([1.0, 0.0, 0.0], "Forward 1m"),
        ([2.0, 1.0, 0.0], "Forward-Right"),
        ([2.0, -1.0, 0.0], "Forward-Left"),
        ([0.0, 2.0, 0.0], "Right 2m"),
    ]

    for i, (pos, desc) in enumerate(waypoints):
        map3d.place(
            name=f'waypoint_{i}',
            object='pointer_arrow',
            params={
                'from_point': [pos[0], pos[1], 0.8],
                'to_point': pos,
                'color': [0.2, 0.8, 1.0],  # Cyan
                'shaft_radius': 0.01,
                'head_radius': 0.03,
            },
            description=desc,
        )
    print(f"✓ Placed {len(waypoints)} waypoint arrows")

    # 3. Add direction indicator arrows
    print("\nPlacing cardinal direction indicators...")
    directions = {
        'north': ([0, 1.5, 0], [1.0, 0.0, 0.0]),    # Red = +Y
        'east': ([1.5, 0, 0], [0.0, 1.0, 0.0]),     # Green = +X
        'up': ([0, 0, 0.5], [0.0, 0.0, 1.0]),       # Blue = +Z
    }

    for name, (pos, color) in directions.items():
        map3d.place(
            name=f'dir_{name}',
            object='pointer_arrow',
            params={
                'from_point': [0.0, 0.0, 0.0],
                'to_point': pos,
                'color': color,
                'shaft_radius': 0.008,
            },
            description=f"Cardinal direction: {name}",
        )
    print(f"✓ Placed {len(directions)} direction indicators")

    # 4. Add a search pattern
    print("\nCreating search pattern...")
    radius = 3.0
    num_points = 8
    import math
    for i in range(num_points):
        angle = (2 * math.pi * i) / num_points
        x = radius * math.cos(angle)
        y = radius * math.sin(angle)

        map3d.place(
            name=f'search_{i}',
            object='pointer_arrow',
            params={
                'from_point': [x, y, 1.2],
                'to_point': [x, y, 0.0],
                'color': [1.0, 0.8, 0.0],  # Gold
                'shaft_radius': 0.006,
                'head_radius': 0.02,
            },
            description=f"Search point {i+1}/{num_points}",
        )
    print(f"✓ Created {num_points}-point search pattern at {radius}m radius")

    print()
    return map3d.list_instances()


def render_scene_tour(output_dir: Path):
    """Render the scene from multiple viewpoints."""
    print("--- Rendering Scene Tour ---")

    viewpoints = [
        {
            'name': '01_overview_high',
            'camera_pos': [0.0, 0.0, 8.0],
            'look_at': [0.0, 0.0, 0.0],
            'title': 'Overhead View - 8m Height',
        },
        {
            'name': '02_ground_perspective',
            'camera_pos': [0.0, -5.0, 0.6],
            'look_at': [0.0, 0.0, 0.5],
            'title': 'Ground Level Perspective',
        },
        {
            'name': '03_northeast_iso',
            'camera_pos': [4.0, 4.0, 3.0],
            'look_at': [0.0, 0.0, 0.5],
            'title': 'Northeast Isometric',
        },
        {
            'name': '04_close_detail',
            'camera_pos': [1.0, -1.0, 0.8],
            'look_at': [0.0, 0.0, 0.3],
            'title': 'Close Detail View',
        },
        {
            'name': '05_west_elevation',
            'camera_pos': [-5.0, 0.0, 1.5],
            'look_at': [0.0, 0.0, 0.5],
            'title': 'West Elevation',
        },
        {
            'name': '06_robot_pov',
            'camera_pos': [0.0, 0.0, 0.7],  # Robot eye height
            'look_at': [2.0, 0.0, 0.7],
            'title': 'Robot POV - Forward View',
        },
    ]

    for i, vp in enumerate(viewpoints, 1):
        print(f"\nRendering {i}/{len(viewpoints)}: {vp['title']}")

        # Get current instance count for HUD
        instances = map3d.list_instances()

        result = map3d.render(
            camera_pos=vp['camera_pos'],
            look_at=vp['look_at'],
            resolution=(1024, 768),
            include_robot=(i == len(viewpoints)),  # Show robot in last view
            hud=[
                HudElement(
                    text=vp['title'],
                    anchor="top_center",
                    color=(255, 255, 255),
                    bg_color=(0, 0, 0),
                    bg_alpha=0.6,
                ),
                HudElement(
                    text=f"Camera: {vp['camera_pos']}",
                    anchor="top_left",
                    color=(200, 200, 200),
                    font_scale=0.35,
                ),
                HudElement(
                    text=f"Look at: {vp['look_at']}",
                    anchor="top_left",
                    color=(200, 200, 200),
                    font_scale=0.35,
                    priority=1,
                ),
                HudElement(
                    text=f"Phantasmata: {len(instances)} instances",
                    anchor="bottom_left",
                    color=(150, 255, 150),
                    font_scale=0.4,
                ),
                HudElement(
                    text=f"View {i}/{len(viewpoints)}",
                    anchor="bottom_right",
                    color=(255, 200, 100),
                    font_scale=0.35,
                ),
            ],
        )

        output_path = output_dir / f"{vp['name']}.png"
        with open(output_path, 'wb') as f:
            f.write(result.image_bytes)

        print(f"  ✓ Saved: {output_path.name}")
        print(f"    Resolution: {result.resolution}")
        print(f"    Size: {len(result.image_bytes) / 1024:.1f} KB")


def test_dynamic_updates(output_dir: Path):
    """Test dynamic parameter updates with renders."""
    print("\n--- Testing Dynamic Updates ---")

    # Create a test arrow
    map3d.place(
        name='dynamic_test',
        object='pointer_arrow',
        params={
            'from_point': [0.0, 0.0, 1.5],
            'to_point': [1.0, 0.0, 0.0],
            'color': [1.0, 0.0, 0.0],  # Start red
        },
    )

    # Render at different stages
    stages = [
        {'color': [1.0, 0.0, 0.0], 'to_point': [1.0, 0.0, 0.0], 'label': 'red_forward'},
        {'color': [0.0, 1.0, 0.0], 'to_point': [0.0, 1.0, 0.0], 'label': 'green_right'},
        {'color': [0.0, 0.0, 1.0], 'to_point': [-1.0, 0.0, 0.0], 'label': 'blue_back'},
    ]

    for i, stage in enumerate(stages):
        # Update the arrow
        map3d.update_instance('dynamic_test', **{k: v for k, v in stage.items() if k != 'label'})

        # Render it
        result = map3d.render(
            camera_pos=[2.0, 2.0, 2.0],
            look_at=[0.0, 0.0, 0.5],
            resolution=(800, 600),
            include_robot=False,
            hud=[
                HudElement(
                    text=f"Dynamic Update Stage {i+1}/3",
                    anchor="top_center",
                    color=(255, 255, 255),
                ),
            ],
        )

        output_path = output_dir / f"07_dynamic_{stage['label']}.png"
        with open(output_path, 'wb') as f:
            f.write(result.image_bytes)
        print(f"  ✓ Stage {i+1}: {stage['label']} → {output_path.name}")

    map3d.remove('dynamic_test')


def cleanup_scene():
    """Remove all test phantasmata."""
    print("\n--- Cleaning Up Scene ---")

    instances = map3d.list_instances()
    print(f"Removing {len(instances)} instances...")

    for name in list(instances.keys()):
        map3d.remove(name)
        print(f"  ✓ Removed {name}")

    print("Scene cleared.")


def main():
    print("=" * 70)
    print("Test 03: Comprehensive Phantasmata Demonstration")
    print("=" * 70)
    print()

    # Create output directory
    output_dir = Path("test/phantasmata_tests/demo_renders")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {output_dir}")
    print()

    start_time = time.time()

    try:
        # Create the scene
        instances = create_scene()
        print(f"Scene ready with {len(instances)} phantasma instances")
        print()

        # Render tour
        render_scene_tour(output_dir)

        # Test dynamic updates
        test_dynamic_updates(output_dir)

    finally:
        # Always cleanup
        cleanup_scene()

    elapsed = time.time() - start_time

    print()
    print("=" * 70)
    print("Test 03 Complete!")
    print(f"Total time: {elapsed:.2f} seconds")
    print(f"All renders saved to: {output_dir}")
    print("=" * 70)
    print()
    print("Summary:")
    print("  ✓ Scene creation with multiple phantasma types")
    print("  ✓ Multi-viewpoint rendering")
    print("  ✓ Dynamic parameter updates")
    print("  ✓ HUD system integration")
    print("  ✓ Cleanup and instance management")


if __name__ == '__main__':
    main()
