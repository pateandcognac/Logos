"""
The static RTAB-Map world I can hold inside Chora.

I load a long-lived point cloud or mesh exported from RTAB-Map asset tooling
and turn it into a phantasma. This gives me stable spatial context that can
last for weeks or months without rebuilding dense geometry during a render.

Note to self:
    This is spatial memory, not navigation truth. My 2D navigation map and
    costmaps remain the authority for driving; this layer helps me see and
    reason about the room in Chora.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
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
    'asset_path': {
        'type': 'path',
        'default': '/home/robot/maps/chora_assets/rtabmap_world/cloud_voxel_0.08.ply',
        'description': 'PLY asset built by tools/chora_build_rtabmap_assets.py',
    },
    'asset_kind': {
        'type': 'choice',
        'default': 'pointcloud',
        'options': ['pointcloud', 'mesh', 'auto'],
        'description': 'Geometry kind to load from the asset path',
    },
    'point_size': {
        'type': 'float',
        'default': 2.0,
        'range': [0.1, 12.0],
        'description': 'Rendered point size for point-cloud assets',
    },
    'max_points': {
        'type': 'int',
        'default': 0,
        'description': 'Optional deterministic point cap; 0 keeps all points',
    },
    'min_z': {
        'type': 'float',
        'default': -1000.0,
        'unit': 'm',
        'description': 'Minimum map-frame height to keep',
    },
    'max_z': {
        'type': 'float',
        'default': 1000.0,
        'unit': 'm',
        'description': 'Maximum map-frame height to keep; use ~2.13m to keep door tops but remove ceiling',
    },
    'camera_clip_radius_m': {
        'type': 'float',
        'default': 0.0,
        'unit': 'm',
        'description': 'Render-time bubble around the virtual camera where this geometry is clipped away',
    },
    'color_mode': {
        'type': 'choice',
        'default': 'asset',
        'options': ['asset', 'uniform', 'height'],
        'description': 'Use stored colors, a uniform color, or height tinting',
    },
    'uniform_color': {
        'type': 'rgb',
        'default': [0.72, 0.78, 0.84],
        'description': 'Color used when color_mode is uniform',
    },
    'reload_token': {
        'type': 'str',
        'default': '',
        'description': 'Change this value to force a cache miss',
    },
}

DYNAMIC = False

_GEOMETRY_CACHE: Dict[Tuple[Any, ...], Any] = {}


def _workspace_root() -> str:
    return os.getcwd()


def _resolve_path(path: str) -> str:
    expanded = os.path.expandvars(os.path.expanduser(str(path)))
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)
    return os.path.abspath(os.path.join(_workspace_root(), expanded))


def _as_rgb(value: Any, default: Tuple[float, float, float]) -> List[float]:
    try:
        vals = [float(x) for x in value]
    except Exception:
        vals = list(default)
    while len(vals) < 3:
        vals.append(default[len(vals)])
    return [max(0.0, min(1.0, vals[i])) for i in range(3)]


def _copy_geometry(kind: str, geometry: Any) -> Any:
    if kind == "mesh":
        return o3d.geometry.TriangleMesh(geometry)
    return o3d.geometry.PointCloud(geometry)


def _filter_pointcloud_z(pcd: Any, min_z: float, max_z: float) -> Any:
    points = np.asarray(pcd.points)
    if points.size == 0:
        return pcd
    mask = (points[:, 2] >= float(min_z)) & (points[:, 2] <= float(max_z))
    if np.all(mask):
        return pcd
    return pcd.select_by_index(np.where(mask)[0].tolist())


def _filter_mesh_z(mesh: Any, min_z: float, max_z: float) -> Any:
    vertices = np.asarray(mesh.vertices)
    if vertices.size == 0:
        return mesh
    mask = (vertices[:, 2] < float(min_z)) | (vertices[:, 2] > float(max_z))
    if not np.any(mask):
        return mesh
    mesh.remove_vertices_by_mask(mask)
    mesh.remove_degenerate_triangles()
    mesh.remove_duplicated_triangles()
    mesh.remove_duplicated_vertices()
    mesh.compute_vertex_normals()
    return mesh


def _limit_pointcloud(pcd: Any, max_points: int) -> Any:
    if max_points <= 0:
        return pcd
    n_points = len(pcd.points)
    if n_points <= max_points:
        return pcd
    indices = np.linspace(0, n_points - 1, int(max_points), dtype=np.int64)
    return pcd.select_by_index(indices.tolist())


def _apply_height_colors(geometry: Any, kind: str) -> None:
    if kind == "mesh":
        coords = np.asarray(geometry.vertices)
    else:
        coords = np.asarray(geometry.points)
    if coords.size == 0:
        return

    z = coords[:, 2]
    z_min = float(np.min(z))
    z_range = float(np.max(z) - z_min)
    if z_range < 1e-6:
        t = np.zeros_like(z)
    else:
        t = (z - z_min) / z_range

    colors = np.zeros((len(coords), 3), dtype=np.float64)
    colors[:, 0] = 0.25 + 0.55 * t
    colors[:, 1] = 0.50 + 0.35 * (1.0 - np.abs(t - 0.5) * 2.0)
    colors[:, 2] = 0.85 - 0.55 * t

    if kind == "mesh":
        geometry.vertex_colors = o3d.utility.Vector3dVector(colors)
    else:
        geometry.colors = o3d.utility.Vector3dVector(colors)


def _apply_colors(geometry: Any, kind: str, color_mode: str, uniform_color: List[float]) -> None:
    if color_mode == "uniform":
        geometry.paint_uniform_color(uniform_color)
        return
    if color_mode == "height":
        _apply_height_colors(geometry, kind)


def _infer_kind(asset_path: str, asset_kind: str) -> str:
    if asset_kind in ("pointcloud", "mesh"):
        return asset_kind
    name = os.path.basename(asset_path).lower()
    if "mesh" in name:
        return "mesh"
    return "pointcloud"


def _load_processed_geometry(params: Dict[str, Any]) -> Tuple[str, Any]:
    asset_path = _resolve_path(params.get('asset_path', SCHEMA['asset_path']['default']))
    if not os.path.exists(asset_path):
        raise RuntimeError("RTAB-Map Chora asset not found: {}".format(asset_path))

    asset_kind = str(params.get('asset_kind', 'pointcloud'))
    kind = _infer_kind(asset_path, asset_kind)
    mtime = os.path.getmtime(asset_path)
    size = os.path.getsize(asset_path)
    max_points = int(params.get('max_points', 0))
    min_z = float(params.get('min_z', -1000.0))
    max_z = float(params.get('max_z', 1000.0))
    color_mode = str(params.get('color_mode', 'asset'))
    uniform_color = _as_rgb(params.get('uniform_color', [0.72, 0.78, 0.84]), (0.72, 0.78, 0.84))
    reload_token = str(params.get('reload_token', ''))

    cache_key = (
        asset_path,
        kind,
        mtime,
        size,
        max_points,
        min_z,
        max_z,
        color_mode,
        tuple(uniform_color),
        reload_token,
    )
    cached = _GEOMETRY_CACHE.get(cache_key)
    if cached is not None:
        return kind, _copy_geometry(kind, cached)

    if kind == "mesh":
        geometry = o3d.io.read_triangle_mesh(asset_path)
        if geometry.is_empty():
            raise RuntimeError("RTAB-Map mesh asset is empty: {}".format(asset_path))
        geometry = _filter_mesh_z(geometry, min_z, max_z)
        geometry.compute_vertex_normals()
    else:
        geometry = o3d.io.read_point_cloud(asset_path)
        if geometry.is_empty():
            raise RuntimeError("RTAB-Map cloud asset is empty: {}".format(asset_path))
        geometry = _filter_pointcloud_z(geometry, min_z, max_z)
        geometry = _limit_pointcloud(geometry, max_points)

    _apply_colors(geometry, kind, color_mode, uniform_color)
    _GEOMETRY_CACHE[cache_key] = _copy_geometry(kind, geometry)
    return kind, geometry


def _make_scene_object(
    name: str,
    kind: str,
    geometry: Any,
    point_size: float,
    camera_clip_radius_m: float,
) -> SceneObject:
    obj = SceneObject(
        name=name,
        kind=kind,
        geometry=geometry,
        render_visible=True,
        raycast_visible=True,
        shader='defaultUnlit' if kind == "pointcloud" else 'defaultLit',
        point_size=point_size,
    )
    obj.camera_clip_radius_m = max(0.0, float(camera_clip_radius_m))
    return obj


def build(params: Dict[str, Any], ctx: Any) -> Optional[Any]:
    """
    Build my static RTAB-Map world layer.

    I load a generated point cloud or mesh artifact, optionally thin it for
    render speed, and hand Chora a normal SceneObject so render() and raycast()
    can treat it like any other phantasma.
    """
    if not _HAS_O3D:
        return None

    kind, geometry = _load_processed_geometry(params)
    point_size = float(params.get('point_size', 2.0))
    camera_clip_radius_m = float(params.get('camera_clip_radius_m', 0.0))

    return _make_scene_object(
        '__auto__',
        kind,
        geometry,
        point_size,
        camera_clip_radius_m,
    )
