# src/logos/phantasmata/grid_overlay.py
"""
A metric grid overlay on my floor for spatial reference.

I draw a regular grid of lines across my floor plane to help with visual
distance estimation and spatial reasoning. The grid makes it easier to judge
distances when looking at my map3d renders.

Note to self:
    Open3D 0.13's LineSet doesn't render in OffscreenRenderer, so I use thin
    box meshes for grid lines. This is a known 0.13 gotcha.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    import open3d as o3d
    _HAS_O3D = True
except ImportError:
    o3d = None
    _HAS_O3D = False

try:
    from logos.map3d import SceneObject
except Exception:
    @dataclass
    class SceneObject:
        name: str
        kind: str
        geometry: Any
        render_visible: bool = True
        raycast_visible: bool = True
        costmap_affects: bool = False
        shader: str = "defaultLit"
        point_size: float = 3.0


SCHEMA = {
    'spacing_m': {
        'type': 'float',
        'default': 1.0,
        'unit': 'm',
        'range': [0.1, 10.0],
        'description': 'Distance between grid lines in meters',
    },
    'extent_m': {
        'type': 'float',
        'default': 10.0,
        'unit': 'm',
        'range': [1.0, 50.0],
        'description': 'How far the grid extends from origin',
    },
    'z': {
        'type': 'float',
        'default': 0.002,
        'unit': 'm',
        'description': 'Height above floor (avoid z-fighting)',
    },
    'line_thickness': {
        'type': 'float',
        'default': 0.005,
        'unit': 'm',
        'description': 'Thickness of grid lines',
    },
    'color': {
        'type': 'rgb',
        'default': [0.3, 0.3, 0.5],
        'description': 'Grid line color',
    },
    'alpha': {
        'type': 'float',
        'default': 0.3,
        'range': [0.0, 1.0],
        'description': 'Grid transparency (not used in 0.13)',
    },
    'center_on_robot': {
        'type': 'bool',
        'default': False,
        'description': 'If True, center grid on robot position',
    },
}

# Grid is static - no need to rebuild each frame
DYNAMIC = False


def _make_thin_box_line(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    thickness: float,
    color: Tuple[float, float, float],
) -> Any:
    """
    Create a thin box mesh representing a line between two points.

    I use thin boxes instead of LineSet because Open3D 0.13's LineSet
    doesn't render in OffscreenRenderer.
    """
    start = np.array(start, dtype=np.float64)
    end = np.array(end, dtype=np.float64)
    direction = end - start
    length = np.linalg.norm(direction)

    if length < 1e-9:
        return None

    # Create box aligned with X axis, centered at origin
    box = o3d.geometry.TriangleMesh.create_box(
        width=length,
        height=thickness,
        depth=thickness,
    )
    # Center the box
    box.translate([-length / 2, -thickness / 2, -thickness / 2])

    # Compute rotation to align X axis with direction
    direction_norm = direction / length
    x_axis = np.array([1.0, 0.0, 0.0])

    rot_axis = np.cross(x_axis, direction_norm)
    rot_axis_len = np.linalg.norm(rot_axis)

    if rot_axis_len > 1e-9:
        rot_axis = rot_axis / rot_axis_len
        dot = np.clip(np.dot(x_axis, direction_norm), -1.0, 1.0)
        angle = np.arccos(dot)

        # Rodrigues' rotation formula
        K = np.array([
            [0, -rot_axis[2], rot_axis[1]],
            [rot_axis[2], 0, -rot_axis[0]],
            [-rot_axis[1], rot_axis[0], 0],
        ])
        R = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)
        box.rotate(R, center=[0, 0, 0])

    # Move to midpoint
    midpoint = (start + end) / 2
    box.translate(midpoint)

    box.paint_uniform_color(color)
    return box


def build(params: Dict[str, Any], ctx: Any) -> Optional[SceneObject]:
    """
    Build the floor grid.

    I create lines along the X and Y axes at regular spacing intervals.
    """
    if not _HAS_O3D:
        return None

    spacing = float(params.get('spacing_m', 1.0))
    extent = float(params.get('extent_m', 10.0))
    z = float(params.get('z', 0.002))
    thickness = float(params.get('line_thickness', 0.005))
    color = params.get('color', [0.3, 0.3, 0.5])
    center_on_robot = params.get('center_on_robot', False)

    # Determine grid center
    cx, cy = 0.0, 0.0
    if center_on_robot and ctx and hasattr(ctx, 'robot_pose') and ctx.robot_pose:
        cx = ctx.robot_pose.get('x', 0.0)
        cy = ctx.robot_pose.get('y', 0.0)
        # Snap to grid
        cx = round(cx / spacing) * spacing
        cy = round(cy / spacing) * spacing

    # Generate grid lines
    lines = []
    half_extent = extent / 2

    # Lines parallel to X axis (varying Y)
    n_lines_y = int(extent / spacing) + 1
    for i in range(n_lines_y):
        y = cy - half_extent + i * spacing
        start = (cx - half_extent, y, z)
        end = (cx + half_extent, y, z)
        line = _make_thin_box_line(start, end, thickness, color)
        if line is not None:
            lines.append(line)

    # Lines parallel to Y axis (varying X)
    n_lines_x = int(extent / spacing) + 1
    for i in range(n_lines_x):
        x = cx - half_extent + i * spacing
        start = (x, cy - half_extent, z)
        end = (x, cy + half_extent, z)
        line = _make_thin_box_line(start, end, thickness, color)
        if line is not None:
            lines.append(line)

    if not lines:
        return None

    # Merge all line meshes
    combined = lines[0]
    for line in lines[1:]:
        combined += line

    combined.compute_vertex_normals()

    return SceneObject(
        name='__auto__',
        kind='mesh',
        geometry=combined,
        render_visible=True,
        raycast_visible=False,  # I don't want clicks hitting the grid
        shader='defaultUnlit',  # Unlit so grid has consistent appearance
    )
