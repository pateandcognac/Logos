# src/logos/phantasmata/occupied_plane.py
"""
A transparent plane at lidar height showing occupied cells from my map.

I render the occupied cells from my ROS occupancy grid as semi-transparent
rectangles at a configurable height. This helps me perceive depth and scale
when comparing my virtual view to physical reality — obstacles appear as
colored blocks at their actual map positions.

Note to self:
    This is useful for debugging navigation issues or verifying that my
    map matches reality. I can enable it via map3d.set_visible() when I
    need to see what my costmap thinks is blocked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import numpy as np

try:
    import open3d as o3d
    _HAS_O3D = True
except ImportError:
    o3d = None
    _HAS_O3D = False

try:
    from logos.map3d import SceneObject, MapSnapshot
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

    MapSnapshot = Any


SCHEMA = {
    'z': {
        'type': 'float',
        'default': 0.70,
        'unit': 'm',
        'description': 'Height of the plane (lidar height ~70cm)',
    },
    'occupied_color': {
        'type': 'rgb',
        'default': [1.0, 0.0, 0.0],
        'description': 'Color for occupied cells (red)',
    },
    'occupied_threshold': {
        'type': 'int',
        'default': 50,
        'range': [0, 100],
        'description': 'Occupancy probability threshold (0-100)',
    },
    'cell_shrink': {
        'type': 'float',
        'default': 0.9,
        'range': [0.1, 1.0],
        'description': 'How much to shrink cells (1.0 = full size)',
    },
    'max_cells': {
        'type': 'int',
        'default': 5000,
        'description': 'Maximum number of cells to render (performance limit)',
    },
}

# I'm dynamic because the map can change as obstacles are detected
DYNAMIC = True


def should_rebuild(params: Dict[str, Any], ctx: Any) -> bool:
    """
    Only rebuild if we have a new map snapshot.

    Note to self:
        For now, I always rebuild when dynamic. In the future, I could track
        map update timestamps and skip rebuilds when the map hasn't changed.
    """
    return True


def build(params: Dict[str, Any], ctx: Any) -> Optional[SceneObject]:
    """
    Build rectangles at occupied cell positions.

    I read the occupancy grid from the MapSnapshot in the context and create
    a small rectangle for each occupied cell.
    """
    if not _HAS_O3D:
        return None

    # Need a map snapshot
    if ctx is None or not hasattr(ctx, 'map_snapshot') or ctx.map_snapshot is None:
        return None

    map_snapshot = ctx.map_snapshot

    # Get map data
    try:
        occupancy = map_snapshot.occupancy_np  # np.ndarray
        resolution = map_snapshot.resolution_m  # meters per cell
        origin_x = map_snapshot.origin_x_m
        origin_y = map_snapshot.origin_y_m
    except AttributeError:
        # MapSnapshot might have different attribute names
        return None

    if occupancy is None or occupancy.size == 0:
        return None

    # Parameters
    z = float(params.get('z', 0.70))
    color = params.get('occupied_color', [1.0, 0.0, 0.0])
    threshold = int(params.get('occupied_threshold', 50))
    shrink = float(params.get('cell_shrink', 0.9))
    max_cells = int(params.get('max_cells', 5000))

    # Find occupied cells
    occupied_indices = np.where(occupancy > threshold)
    if len(occupied_indices[0]) == 0:
        return None

    n_cells = len(occupied_indices[0])
    if n_cells > max_cells:
        # Subsample to stay within performance budget
        indices = np.random.choice(n_cells, max_cells, replace=False)
        row_indices = occupied_indices[0][indices]
        col_indices = occupied_indices[1][indices]
    else:
        row_indices = occupied_indices[0]
        col_indices = occupied_indices[1]

    # Create rectangles for each occupied cell
    cell_size = resolution * shrink
    half_cell = cell_size / 2
    cell_height = 0.01  # Thin rectangles

    rectangles = []

    for i in range(len(row_indices)):
        row = row_indices[i]
        col = col_indices[i]

        # Convert grid indices to world coordinates
        # Occupancy grid: row = Y direction, col = X direction
        world_x = origin_x + (col + 0.5) * resolution
        world_y = origin_y + (row + 0.5) * resolution

        # Create a thin box
        box = o3d.geometry.TriangleMesh.create_box(
            width=cell_size,
            height=cell_size,
            depth=cell_height,
        )
        # Center and position
        box.translate([
            world_x - half_cell,
            world_y - half_cell,
            z - cell_height / 2,
        ])
        rectangles.append(box)

    if not rectangles:
        return None

    # Merge all rectangles
    combined = rectangles[0]
    for rect in rectangles[1:]:
        combined += rect

    combined.paint_uniform_color(color)
    combined.compute_vertex_normals()

    return SceneObject(
        name='__auto__',
        kind='mesh',
        geometry=combined,
        render_visible=True,
        raycast_visible=False,  # Don't want clicks hitting this overlay
        shader='defaultUnlit',
    )
