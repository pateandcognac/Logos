#!/usr/bin/env python3
<py>
"""
Test 02: Rendering with Phantasmata

I'm testing the full render pipeline with various phantasmata visible.
This generates multiple rendered images from different viewpoints to verify
that geometry is properly placed and rendered.

Author: Logos (with Claude's help)
Date: 2026-02-28
"""

# from __future__ import annotations
import sys
import os
from pathlib import Path

# Add logos to path if running standalone
# sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../src'))

import logos
from logos import map3d
from logos.map3d import HudElement


def main():
    print("=" * 70)
    print("Test 02: Rendering with Phantasmata")
    print("=" * 70)
    print()

    # Create output directory
    output_dir = Path("test/phantasmata_tests/renders")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"Saving renders to: {output_dir}")
    print()

    # ---- Setup: Place phantasmata ----
    print("--- Setup: Placing Phantasmata ---")

    # Metric grid for reference
    map3d.place(
        name='metric_grid',
        object='grid_overlay',
        params={
            'spacing_m': 1.0,
            'extent_m': 8.0,
            'color': [0.3, 0.3, 0.5],
        },
        description="1-meter grid for scale reference",
    )
    print("✓ Placed metric_grid")

    # Pointer arrow showing forward direction
    map3d.place(
        name='forward_arrow',
        object='pointer_arrow',
        params={
            'from_point': [0.0, 0.0, 0.5],
            'to_point': [2.0, 0.0, 0.0],
            'color': [0.0, 1.0, 0.0],  # Green for forward
        },
        description="Arrow showing +X (forward) direction",
    )
    print("✓ Placed forward_arrow")

    # Another arrow showing a diagonal
    map3d.place(
        name='diagonal_arrow',
        object='pointer_arrow',
        params={
            'from_point': [1.0, 1.0, 1.0],
            'to_point': [3.0, 2.0, 0.0],
            'color': [1.0, 0.5, 0.0],  # Orange
        },
        description="Diagonal arrow",
    )
    print("✓ Placed diagonal_arrow")
    print()

    # ---- Render 1: Top-down view ----
    print("--- Render 1: Top-Down View ---")
    result = map3d.render(
        camera_pos_relative=[2.0, 0.0, 5.0],     # 5m above, looking at (2, 0)
        look_at_relative=[2.0, 0.0, 0.0],
        resolution=(800, 800),
        include_robot=False,  # Just phantasmata
        hud=[
            HudElement(
                text="Top-Down View (5m height)",
                anchor="top_center",
                color=(255, 255, 255),
            ),
        ],
    )

    output_path = output_dir / "01_top_down.png"
    with open(output_path, 'wb') as f:
        f.write(result.image_bytes)
    print(f"✓ Saved: {output_path}")
    print(f"  Resolution: {result.resolution}")
    print(f"  Render ID: {result.render_id}")
    print()

    # ---- Render 2: Ground-level perspective ----
    print("--- Render 2: Ground-Level Perspective ---")
    result = map3d.render(
        camera_pos_relative=[0.0, -3.0, 0.5],    # 3m back, eye height
        look_at_relative=[2.0, 0.0, 0.5],        # Looking forward and slightly up
        resolution=(1024, 768),
        include_robot=False,
        hud=[
            HudElement(
                text="Ground-Level View",
                anchor="top_center",
                color=(255, 255, 255),
            ),
            HudElement(
                text="Camera: (0, -3, 0.5)",
                anchor="bottom_left",
                color=(200, 200, 200),
                font_scale=0.4,
            ),
        ],
    )

    output_path = output_dir / "02_ground_level.png"
    with open(output_path, 'wb') as f:
        f.write(result.image_bytes)
    print(f"✓ Saved: {output_path}")
    print()

    # ---- Render 3: Isometric view ----
    print("--- Render 3: Isometric View ---")
    result = map3d.render(
        camera_pos_relative=[4.0, -4.0, 3.0],    # Diagonal, elevated
        look_at_relative=[1.0, 0.0, 0.0],
        resolution=(800, 800),
        include_robot=False,
        hud=[
            HudElement(
                text="Isometric View",
                anchor="top_center",
                color=(255, 255, 255),
            ),
        ],
    )

    output_path = output_dir / "03_isometric.png"
    with open(output_path, 'wb') as f:
        f.write(result.image_bytes)
    print(f"✓ Saved: {output_path}")
    print()

    # ---- Render 4: With robot ----
    print("--- Render 4: Including Robot Self-Model ---")
    result = map3d.render(
        camera_pos_relative=[2.0, -2.0, 1.0],
        look_at_relative=[0.0, 0.0, 0.5],
        resolution=(800, 800),
        include_robot=True,  # Show my self-model!
        hud=[
            HudElement(
                text="My Self-Model",
                anchor="top_center",
                color=(100, 255, 255),
            ),
            HudElement(
                text="This is how I see myself in my mind palace",
                anchor="bottom_center",
                color=(200, 200, 200),
                font_scale=0.4,
            ),
        ],
    )

    output_path = output_dir / "04_with_robot.png"
    with open(output_path, 'wb') as f:
        f.write(result.image_bytes)
    print(f"✓ Saved: {output_path}")
    print()

    # ---- Render 5: High resolution detail ----
    print("--- Render 5: High Resolution Detail ---")
    result = map3d.render(
        camera_pos_relative=[1.5, -1.5, 0.8],
        look_at_relative=[2.0, 0.0, 0.2],
        resolution=(1920, 1080),  # Full HD
        include_robot=True,
        hud=[
            HudElement(
                text="High Resolution Render (1920x1080)",
                anchor="top_left",
                color=(255, 255, 255),
            ),
            HudElement(
                text=f"Render ID: {result.render_id if hasattr(result, 'render_id') else 'N/A'}",
                anchor="bottom_right",
                color=(150, 150, 150),
                font_scale=0.35,
            ),
        ],
    )

    output_path = output_dir / "05_high_res.png"
    with open(output_path, 'wb') as f:
        f.write(result.image_bytes)
    print(f"✓ Saved: {output_path}")
    print(f"  File size: {len(result.image_bytes) / 1024:.1f} KB")
    print()

    # ---- Render 6: Multiple HUD elements ----
    print("--- Render 6: Complex HUD Demonstration ---")
    result = map3d.render(
        camera_pos_relative=[3.0, 0.0, 2.0],
        look_at_relative=[0.0, 0.0, 0.5],
        resolution=(800, 600),
        include_robot=True,
        hud=[
            HudElement(
                text="Multi-Element HUD Test",
                anchor="top_center",
                color=(255, 255, 255),
                bg_color=(0, 0, 100),
                bg_alpha=0.7,
                priority=0,
            ),
            HudElement(
                text="Camera Position: (3.0, 0.0, 2.0)",
                anchor="top_left",
                color=(200, 200, 255),
                font_scale=0.4,
                priority=1,
            ),
            HudElement(
                text="Looking at: (0, 0, 0.5)",
                anchor="top_left",
                color=(200, 200, 255),
                font_scale=0.4,
                priority=2,
            ),
            HudElement(
                text="Grid: 1m spacing",
                anchor="bottom_left",
                color=(150, 255, 150),
                font_scale=0.4,
            ),
            HudElement(
                text="Phantasmata Active: 3",
                anchor="bottom_left",
                color=(150, 255, 150),
                font_scale=0.4,
                priority=1,
            ),
            HudElement(
                text="Test 02 - Rendering Pipeline",
                anchor="bottom_right",
                color=(255, 200, 100),
                font_scale=0.35,
            ),
        ],
    )

    output_path = output_dir / "06_complex_hud.png"
    with open(output_path, 'wb') as f:
        f.write(result.image_bytes)
    print(f"✓ Saved: {output_path}")
    print()

    # ---- Cleanup ----
    print("--- Cleanup ---")
    map3d.remove('metric_grid')
    map3d.remove('forward_arrow')
    map3d.remove('diagonal_arrow')
    print("✓ Removed all test phantasmata")
    print()

    print("=" * 70)
    print("Test 02 Complete!")
    print(f"Generated 6 renders in: {output_dir}")
    print("All rendering operations succeeded.")
    print("=" * 70)

main()

loop_cognition=False
</py>

if __name__ == '__main__':
    main()
