# src/logos/phantasmata/pointer_arrow.py
"""
A 3D arrow for pointing at things in my mind palace.

I use this to visually indicate "this is the spot I mean" when communicating
about spatial locations. The arrow points from one world coordinate to another,
making it easy to highlight navigation goals, objects of interest, or any
specific location I want to draw attention to.

This is typically placed programmatically via map3d.place() rather than
configured in mind_palace.yaml, since it's usually ephemeral.

Example usage:
    # Point at a navigation goal
    map3d.place(
        name='nav_target',
        object='pointer_arrow',
        params={
            'from_point': [0, 0, 2.0],  # 2m above floor
            'to_point': [3.5, 1.2, 0.0],  # Target location on floor
            'color': [1.0, 0.5, 0.0],  # Orange
        }
    )

    # Remove when done
    map3d.remove('nav_target')
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
    'from_point': {
        'type': 'list',
        'default': [0.0, 0.0, 1.5],
        'description': 'Arrow start point [x, y, z] in world coordinates',
    },
    'to_point': {
        'type': 'list',
        'default': [1.0, 0.0, 0.0],
        'description': 'Arrow end point [x, y, z] in world coordinates',
    },
    'color': {
        'type': 'rgb',
        'default': [1.0, 0.2, 0.2],
        'description': 'Arrow color (red by default)',
    },
    'shaft_radius': {
        'type': 'float',
        'default': 0.015,
        'unit': 'm',
        'description': 'Radius of the arrow shaft',
    },
    'head_radius': {
        'type': 'float',
        'default': 0.04,
        'unit': 'm',
        'description': 'Radius of the arrow head cone',
    },
    'head_length': {
        'type': 'float',
        'default': 0.08,
        'unit': 'm',
        'description': 'Length of the arrow head cone',
    },
    'from_robot': {
        'type': 'bool',
        'default': False,
        'description': 'If True, start from robot position (overrides from_point)',
    },
    'from_offset_z': {
        'type': 'float',
        'default': 0.5,
        'unit': 'm',
        'description': 'Z offset when from_robot is True',
    },
}

# I'm dynamic because the target might change, but typically I'm placed
# and removed programmatically rather than persisting across renders.
DYNAMIC = False


def build(params: Dict[str, Any], ctx: Any) -> Optional[SceneObject]:
    """
    Build a 3D arrow from start to end point.

    The arrow consists of a cylindrical shaft and a conical head.
    """
    if not _HAS_O3D:
        return None

    # Resolve start point
    from_robot = params.get('from_robot', False)
    if from_robot and ctx and hasattr(ctx, 'robot_pose') and ctx.robot_pose:
        start = np.array([
            ctx.robot_pose.get('x', 0.0),
            ctx.robot_pose.get('y', 0.0),
            params.get('from_offset_z', 0.5),
        ], dtype=np.float64)
    else:
        from_point = params.get('from_point', [0.0, 0.0, 1.5])
        start = np.array(from_point, dtype=np.float64)

    to_point = params.get('to_point', [1.0, 0.0, 0.0])
    end = np.array(to_point, dtype=np.float64)

    color = params.get('color', [1.0, 0.2, 0.2])
    shaft_radius = float(params.get('shaft_radius', 0.015))
    head_radius = float(params.get('head_radius', 0.04))
    head_length = float(params.get('head_length', 0.08))

    direction = end - start
    length = np.linalg.norm(direction)

    if length < 1e-9:
        return None

    direction_norm = direction / length

    # Shaft length excludes head
    shaft_length = max(0.0, length - head_length)

    parts = []

    if shaft_length > 0:
        # Create shaft cylinder aligned with Z axis
        shaft = o3d.geometry.TriangleMesh.create_cylinder(
            radius=shaft_radius,
            height=shaft_length,
            resolution=12,
        )
        # Translate so bottom is at origin
        shaft.translate([0, 0, shaft_length / 2])
        parts.append(shaft)

    # Create head cone
    head = o3d.geometry.TriangleMesh.create_cone(
        radius=head_radius,
        height=head_length,
        resolution=12,
    )
    head.translate([0, 0, shaft_length])
    parts.append(head)

    # Merge parts
    arrow = parts[0]
    for p in parts[1:]:
        arrow += p

    # Rotate to align with direction (from Z axis to direction)
    z_axis = np.array([0.0, 0.0, 1.0])
    rot_axis = np.cross(z_axis, direction_norm)
    rot_axis_len = np.linalg.norm(rot_axis)

    if rot_axis_len > 1e-9:
        rot_axis = rot_axis / rot_axis_len
        dot = np.clip(np.dot(z_axis, direction_norm), -1.0, 1.0)
        angle = np.arccos(dot)

        K = np.array([
            [0, -rot_axis[2], rot_axis[1]],
            [rot_axis[2], 0, -rot_axis[0]],
            [-rot_axis[1], rot_axis[0], 0],
        ])
        R = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)
        arrow.rotate(R, center=[0, 0, 0])
    elif np.dot(z_axis, direction_norm) < 0:
        # 180 degree rotation (pointing down)
        arrow.rotate(np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]]), center=[0, 0, 0])

    # Translate to start position
    arrow.translate(start)

    # Color and normals
    arrow.paint_uniform_color(color)
    arrow.compute_vertex_normals()

    return SceneObject(
        name='__auto__',
        kind='mesh',
        geometry=arrow,
        render_visible=True,
        raycast_visible=True,  # Can click on the arrow
        shader='defaultLit',
    )
