# src/logos/phantasmata/phantasma_convention.py
"""
The phantasma convention — data structures and utilities for phantasma plugins.

This module defines PhantasmaContext (the runtime context passed to phantasma
functions) and schema validation helpers. It's the contract between Map3d
and the phantasmata plugins.

A phantasma is a Python module that defines 3D geometry and/or HUD overlays.
Each module must implement:
    - SCHEMA: dict describing accepted parameters
    - build(params, ctx) -> SceneObject | List[SceneObject] | None

Optional:
    - DYNAMIC: bool (default False) — rebuild every render vs cache
    - hud(params, ctx) -> List[HudElement] | None
    - should_rebuild(params, ctx) -> bool — gate expensive rebuilds
    - cleanup(ctx) -> None — called when instance is removed
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING
import math

if TYPE_CHECKING:
    import numpy as np

# Re-export SceneObject from map3d for convenience
# (phantasmata can import directly from here)
try:
    from logos.map3d import SceneObject, HudElement, MapSnapshot
except Exception:
    # For standalone testing or when map3d isn't available yet
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
        albedo_image: Any = None
        base_color_rgba: Optional[Tuple[float, float, float, float]] = None
        has_alpha: bool = False

    @dataclass
    class HudElement:
        text: str
        anchor: str = "top_left"
        color: Tuple[int, int, int] = (255, 255, 255)
        bg_color: Optional[Tuple[int, int, int]] = (0, 0, 0)
        bg_alpha: float = 0.4
        font_scale: float = 0.45
        thickness: int = 1
        font: int = 0
        margin_px: int = 8
        priority: int = 0

    MapSnapshot = Any  # type: ignore


__all__ = [
    "PhantasmaContext",
    "SceneObject",
    "HudElement",
    "MapSnapshot",
    "euler_rpy_deg_to_rot_matrix",
    "make_transform_matrix",
    "apply_pose_to_geometry",
    "SCHEMA_TYPES",
]


# ---- Schema Types Documentation ----

SCHEMA_TYPES = {
    'float': {
        'python_type': float,
        'description': 'Floating point number',
        'optional_keys': ['range', 'unit'],
    },
    'int': {
        'python_type': int,
        'description': 'Integer',
        'optional_keys': ['range'],
    },
    'bool': {
        'python_type': bool,
        'description': 'Boolean true/false',
    },
    'str': {
        'python_type': str,
        'description': 'Text string',
    },
    'rgb': {
        'python_type': list,
        'description': '3-element list of floats [R,G,B] in 0.0-1.0 range',
    },
    'rgba': {
        'python_type': list,
        'description': '4-element list of floats [R,G,B,A] in 0.0-1.0 range',
    },
    'choice': {
        'python_type': str,
        'description': 'One of several predefined options',
        'required_keys': ['options'],
    },
    'path': {
        'python_type': str,
        'description': 'Filesystem path (relative to workspace)',
    },
    'list': {
        'python_type': list,
        'description': 'Generic list of values',
    },
}


@dataclass
class PhantasmaContext:
    """
    Runtime context I receive in my build() and hud() calls.

    This is my window into the Logos ecosystem during a render. I can access
    the current robot pose, TF buffer, map state, and even the shared REPL
    namespace where the AI's Python variables live.

    Attributes:
        config: The logos.config dict (runtime configuration/preferences)
        ns: The shared REPL namespace (Python interpreter globals).
            This lets me read variables the AI set during cognition.
        tf_buffer: tf2_ros.Buffer for TF lookups
        robot_pose: Current robot pose as dict with keys:
            'x', 'y', 'z', 'yaw', 'roll', 'pitch' (map frame)
            None if TF unavailable.
        map_snapshot: Current frozen occupancy grid for this render
        world_frame: Active world frame ("map", "odom", or "")
        instance_name: My name from mind_palace.yaml
        instance_config: My full configuration entry from mind_palace.yaml
        render_timestamp: Unix timestamp of this render
        camera_world_pos: Virtual camera XYZ in the active world frame.
        look_at_world_pos: Virtual camera target XYZ in the active world frame.
        warn: Callback for adding a message to this render's warnings.
    """
    # Logos ecosystem
    config: Dict[str, Any] = field(default_factory=dict)
    ns: Dict[str, Any] = field(default_factory=dict)

    # ROS convenience
    tf_buffer: Any = None
    robot_pose: Optional[Dict[str, float]] = None

    # Map3d-specific
    map_snapshot: Any = None  # MapSnapshot
    world_frame: str = "map"

    # Instance metadata
    instance_name: str = ""
    instance_config: Dict[str, Any] = field(default_factory=dict)

    # Timing
    render_timestamp: float = 0.0

    # Virtual camera convenience
    camera_world_pos: Any = None
    look_at_world_pos: Any = None

    # Render diagnostics
    warn: Optional[Callable[[str], None]] = None


# ---- Geometry Transform Helpers ----
# These are utilities that phantasmata commonly need for positioning geometry.
# Open3D 0.13 compatible.


def euler_rpy_deg_to_rot_matrix(
    roll: float,
    pitch: float,
    yaw: float,
) -> "np.ndarray":
    """
    Convert Roll/Pitch/Yaw in degrees to a 3x3 rotation matrix.

    Uses ROS convention (XYZ intrinsic rotations):
    R = Rz(yaw) * Ry(pitch) * Rx(roll)

    Args:
        roll: Rotation about X axis in degrees
        pitch: Rotation about Y axis in degrees
        yaw: Rotation about Z axis in degrees

    Returns:
        3x3 numpy rotation matrix
    """
    import numpy as np

    r = math.radians(roll)
    p = math.radians(pitch)
    y = math.radians(yaw)

    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)

    # Rz(yaw) * Ry(pitch) * Rx(roll)
    rot = np.array([
        [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
        [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
        [-sp,     cp * sr,                cp * cr],
    ], dtype=np.float64)

    return rot


def make_transform_matrix(
    position: Optional[Tuple[float, float, float]] = None,
    rpy_deg: Optional[Tuple[float, float, float]] = None,
) -> "np.ndarray":
    """
    Build a 4x4 transformation matrix from position and RPY angles.

    Args:
        position: (x, y, z) translation in meters. Defaults to (0, 0, 0).
        rpy_deg: (roll, pitch, yaw) rotation in degrees. Defaults to (0, 0, 0).

    Returns:
        4x4 numpy transformation matrix
    """
    import numpy as np

    mat = np.eye(4, dtype=np.float64)

    if rpy_deg is not None:
        mat[:3, :3] = euler_rpy_deg_to_rot_matrix(*rpy_deg)

    if position is not None:
        mat[:3, 3] = position

    return mat


def apply_pose_to_geometry(
    geometry: Any,
    pose_config: Optional[Dict[str, Any]],
) -> Any:
    """
    Apply a pose configuration to Open3D geometry.

    The pose_config dict can contain:
        - position: [x, y, z] in meters
        - rpy_deg: [roll, pitch, yaw] in degrees
        - frame: TF frame override (not handled here — Map3d handles this)

    Args:
        geometry: Open3D geometry object (TriangleMesh, PointCloud, etc.)
        pose_config: Pose configuration dict from mind_palace.yaml

    Returns:
        The transformed geometry (modified in-place and returned)
    """
    if pose_config is None:
        return geometry

    position = pose_config.get('position')
    rpy_deg = pose_config.get('rpy_deg')

    if position is None and rpy_deg is None:
        return geometry

    # Build transform matrix
    pos = tuple(position) if position else (0.0, 0.0, 0.0)
    rot = tuple(rpy_deg) if rpy_deg else (0.0, 0.0, 0.0)
    mat = make_transform_matrix(pos, rot)

    # Apply to geometry
    geometry.transform(mat)
    return geometry


# ---- Geometry Building Helpers ----
# Common patterns for building phantasma geometry with Open3D 0.13


def make_thin_box_line(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    thickness: float = 0.005,
    color: Tuple[float, float, float] = (0.5, 0.5, 0.5),
) -> Any:
    """
    Create a thin box mesh representing a line between two points.

    Open3D 0.13's LineSet doesn't render in OffscreenRenderer, so I use
    thin box meshes instead. This is a known 0.13 gotcha.

    Args:
        start: Start point (x, y, z)
        end: End point (x, y, z)
        thickness: Width/height of the box cross-section
        color: RGB color (0.0-1.0)

    Returns:
        Open3D TriangleMesh representing the line
    """
    import numpy as np

    try:
        import open3d as o3d
    except ImportError:
        raise RuntimeError("Open3D required for geometry creation")

    start = np.array(start, dtype=np.float64)
    end = np.array(end, dtype=np.float64)
    direction = end - start
    length = np.linalg.norm(direction)

    if length < 1e-9:
        # Zero-length line, return empty mesh
        return o3d.geometry.TriangleMesh()

    # Create box centered at origin, aligned with X axis
    box = o3d.geometry.TriangleMesh.create_box(
        width=length,
        height=thickness,
        depth=thickness,
    )
    # Center it
    box.translate([-length / 2, -thickness / 2, -thickness / 2])

    # Compute rotation to align X axis with direction
    direction_norm = direction / length
    x_axis = np.array([1.0, 0.0, 0.0])

    # Rotation axis is cross product
    rot_axis = np.cross(x_axis, direction_norm)
    rot_axis_len = np.linalg.norm(rot_axis)

    if rot_axis_len > 1e-9:
        rot_axis = rot_axis / rot_axis_len
        # Rotation angle is acos of dot product
        dot = np.clip(np.dot(x_axis, direction_norm), -1.0, 1.0)
        angle = np.arccos(dot)

        # Rodrigues' rotation formula -> rotation matrix
        K = np.array([
            [0, -rot_axis[2], rot_axis[1]],
            [rot_axis[2], 0, -rot_axis[0]],
            [-rot_axis[1], rot_axis[0], 0],
        ])
        R = np.eye(3) + np.sin(angle) * K + (1 - np.cos(angle)) * (K @ K)
        box.rotate(R, center=[0, 0, 0])

    # Translate to midpoint
    midpoint = (start + end) / 2
    box.translate(midpoint)

    # Color
    box.paint_uniform_color(color)
    box.compute_vertex_normals()

    return box


def make_arrow(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    shaft_radius: float = 0.01,
    head_radius: float = 0.025,
    head_length: float = 0.05,
    color: Tuple[float, float, float] = (1.0, 0.0, 0.0),
) -> Any:
    """
    Create an arrow mesh pointing from start to end.

    Args:
        start: Start point (x, y, z)
        end: End point (x, y, z)
        shaft_radius: Radius of the arrow shaft
        head_radius: Radius of the arrow head cone
        head_length: Length of the arrow head cone
        color: RGB color (0.0-1.0)

    Returns:
        Open3D TriangleMesh representing the arrow
    """
    import numpy as np

    try:
        import open3d as o3d
    except ImportError:
        raise RuntimeError("Open3D required for geometry creation")

    start = np.array(start, dtype=np.float64)
    end = np.array(end, dtype=np.float64)
    direction = end - start
    length = np.linalg.norm(direction)

    if length < 1e-9:
        return o3d.geometry.TriangleMesh()

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

    # Rotate to align with direction
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
        # 180 degree rotation (pointing opposite direction)
        arrow.rotate(np.array([[1, 0, 0], [0, -1, 0], [0, 0, -1]]), center=[0, 0, 0])

    # Translate to start position
    arrow.translate(start)

    # Color and normals
    arrow.paint_uniform_color(color)
    arrow.compute_vertex_normals()

    return arrow
