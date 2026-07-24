"""
I render my persistent waypoint registry as one semantic Chora layer.

The waypoint records belong to logos.waypoints, not to this phantasma. I turn
those records into optional OpenMoji decals plus precise pose markers so I can
recognize a place visually without losing its actionable floor pose.

Note to self:
    Camera-facing icons are deliberately cylindrical billboards: they rotate
    around world Z but remain upright. My heading arrow never follows the
    virtual camera; it always preserves the saved robot yaw.
"""

from __future__ import annotations

from pathlib import Path
import math
import threading
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

try:
    import open3d as o3d
    _HAS_O3D = True
except ImportError:
    o3d = None
    _HAS_O3D = False

from logos.phantasmata.phantasma_convention import (
    SceneObject,
    make_arrow,
)


SCHEMA = {
    "default_mode": {
        "type": "choice",
        "default": "camera_billboard",
        "options": ["floor", "pose_billboard", "camera_billboard", "marker"],
        "description": "How I draw waypoint emoji without a per-record override",
    },
    "default_scale_m": {
        "type": "float",
        "default": 0.35,
        "unit": "m",
        "description": "Default width and height of an emoji marker",
    },
    "default_icon_height_m": {
        "type": "float",
        "default": 0.25,
        "unit": "m",
        "description": "Clearance between the floor pose and an upright icon",
    },
    "default_marker": {
        "type": "choice",
        "default": "pin",
        "options": ["none", "pin", "axes"],
        "description": "Precise pose geometry drawn alongside the emoji",
    },
    "default_show_heading": {
        "type": "bool",
        "default": True,
        "description": "Draw my saved yaw as a floor arrow",
    },
    "marker_color": {
        "type": "rgb",
        "default": [1.0, 0.55, 0.08],
        "description": "Color of pin markers and heading arrows",
    },
}


# At least camera_billboard geometry depends on the current virtual camera.
DYNAMIC = True

_TEXTURE_CACHE: Dict[str, Tuple[int, Any]] = {}
_TEXTURE_CACHE_LOCK = threading.Lock()


def _warn(ctx: Any, message: str) -> None:
    callback = getattr(ctx, "warn", None)
    if callable(callback):
        callback(message)
    else:
        print("[waypoints] Warning: {}".format(message))


def _emoji_candidate_filenames(emoji: str) -> List[str]:
    """Translate a Unicode grapheme into likely OpenMoji PNG filenames."""
    codepoints = ["{:04X}".format(ord(character)) for character in emoji]
    variants = [codepoints]

    without_variation = [
        codepoint for codepoint in codepoints if codepoint not in ("FE0E", "FE0F")
    ]
    if without_variation != codepoints:
        variants.append(without_variation)

    filenames: List[str] = []
    for variant in variants:
        if not variant:
            continue
        filename = "{}.png".format("-".join(variant))
        if filename not in filenames:
            filenames.append(filename)
    return filenames


def _openmoji_root(ctx: Any) -> Path:
    config = getattr(ctx, "config", {})
    waypoint_config = config.get("waypoints", {}) if isinstance(config, dict) else {}
    configured = (
        waypoint_config.get("openmoji_dir")
        if isinstance(waypoint_config, dict)
        else None
    )
    if not configured:
        configured = "~/robot_workspaces/shared/openmoji-72x72-color"
    return Path(str(configured)).expanduser()


def _resolve_emoji_path(
    waypoint: Dict[str, Any],
    root: Path,
) -> Optional[Path]:
    render = waypoint.get("render", {})
    explicit = render.get("emoji_file") if isinstance(render, dict) else None
    if explicit:
        candidate = root / Path(str(explicit)).name
        return candidate if candidate.is_file() else None

    emoji = waypoint.get("emoji")
    if not isinstance(emoji, str) or not emoji:
        return None

    for filename in _emoji_candidate_filenames(emoji):
        candidate = root / filename
        if candidate.is_file():
            return candidate
    return None


def _load_texture(path: Path) -> Optional[Any]:
    """Decode and cache one transparent OpenMoji image for Open3D."""
    try:
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        return None

    cache_key = str(path)
    with _TEXTURE_CACHE_LOCK:
        cached = _TEXTURE_CACHE.get(cache_key)
        if cached is not None and cached[0] == mtime_ns:
            return cached[1]

    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        return None

    if image.ndim == 2:
        rgba = cv2.cvtColor(image, cv2.COLOR_GRAY2RGBA)
    elif image.shape[2] == 3:
        rgba = cv2.cvtColor(image, cv2.COLOR_BGR2RGBA)
    elif image.shape[2] == 4:
        rgba = cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA)
    else:
        return None

    # Open3D's UV origin is at the bottom-left; OpenCV's image origin is top-left.
    rgba = np.ascontiguousarray(np.flipud(rgba))
    texture = o3d.geometry.Image(rgba)

    with _TEXTURE_CACHE_LOCK:
        _TEXTURE_CACHE[cache_key] = (mtime_ns, texture)
    return texture


def _make_textured_quad(
    vertices: np.ndarray,
    double_sided: bool,
) -> Any:
    """Build a square mesh with conventional bottom-left UV coordinates."""
    front_triangles = [[0, 1, 2], [0, 2, 3]]
    front_uvs = [
        [0.0, 0.0], [1.0, 0.0], [1.0, 1.0],
        [0.0, 0.0], [1.0, 1.0], [0.0, 1.0],
    ]
    triangles = list(front_triangles)
    uvs = list(front_uvs)

    if double_sided:
        triangles.extend([[2, 1, 0], [3, 2, 0]])
        uvs.extend([
            [1.0, 1.0], [1.0, 0.0], [0.0, 0.0],
            [0.0, 1.0], [1.0, 1.0], [0.0, 0.0],
        ])

    mesh = o3d.geometry.TriangleMesh()
    mesh.vertices = o3d.utility.Vector3dVector(
        np.asarray(vertices, dtype=np.float64)
    )
    mesh.triangles = o3d.utility.Vector3iVector(
        np.asarray(triangles, dtype=np.int32)
    )
    mesh.triangle_uvs = o3d.utility.Vector2dVector(
        np.asarray(uvs, dtype=np.float64)
    )
    mesh.compute_vertex_normals()
    return mesh


def _floor_icon(
    position: np.ndarray,
    yaw_deg: float,
    scale_m: float,
) -> Any:
    yaw = math.radians(yaw_deg)
    forward = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    image_right = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
    center = np.array(position, dtype=np.float64)
    center[2] += 0.008
    half = scale_m / 2.0

    vertices = np.array([
        center - image_right * half - forward * half,
        center + image_right * half - forward * half,
        center + image_right * half + forward * half,
        center - image_right * half + forward * half,
    ])
    return _make_textured_quad(vertices, double_sided=True)


def _upright_icon(
    position: np.ndarray,
    normal: np.ndarray,
    scale_m: float,
    icon_height_m: float,
) -> Any:
    up = np.array([0.0, 0.0, 1.0])
    normal = np.asarray(normal, dtype=np.float64)
    normal[2] = 0.0
    normal_length = np.linalg.norm(normal)
    if normal_length < 1e-9:
        normal = np.array([1.0, 0.0, 0.0])
    else:
        normal /= normal_length

    image_right = np.cross(up, normal)
    half = scale_m / 2.0
    bottom_center = np.asarray(position, dtype=np.float64).copy()
    bottom_center[2] += icon_height_m
    top_center = bottom_center + up * scale_m

    vertices = np.array([
        bottom_center - image_right * half,
        bottom_center + image_right * half,
        top_center + image_right * half,
        top_center - image_right * half,
    ])
    return _make_textured_quad(vertices, double_sided=True)


def _combine_meshes(parts: List[Any]) -> Optional[Any]:
    parts = [part for part in parts if part is not None and not part.is_empty()]
    if not parts:
        return None

    combined = parts[0]
    for part in parts[1:]:
        combined += part
    combined.compute_vertex_normals()
    return combined


def _pin_parts(
    position: np.ndarray,
    scale_m: float,
    color: List[float],
) -> List[Any]:
    """Make a compact floor pin centered on the exact saved pose."""
    radius = max(0.018, scale_m * 0.07)
    base_height = max(0.008, scale_m * 0.025)
    stem_height = max(0.10, scale_m * 0.34)

    base = o3d.geometry.TriangleMesh.create_cylinder(
        radius=radius * 1.35,
        height=base_height,
        resolution=20,
    )
    base.translate(position + np.array([0.0, 0.0, base_height / 2.0]))
    base.paint_uniform_color(color)

    stem = o3d.geometry.TriangleMesh.create_cylinder(
        radius=radius * 0.32,
        height=stem_height,
        resolution=12,
    )
    stem.translate(position + np.array([0.0, 0.0, stem_height / 2.0]))
    stem.paint_uniform_color(color)

    head = o3d.geometry.TriangleMesh.create_sphere(
        radius=radius,
        resolution=16,
    )
    head.translate(position + np.array([0.0, 0.0, stem_height]))
    head.paint_uniform_color(color)
    return [base, stem, head]


def _axes_parts(
    position: np.ndarray,
    yaw_deg: float,
    scale_m: float,
) -> List[Any]:
    """Make standard RGB pose axes with yaw applied around world Z."""
    yaw = math.radians(yaw_deg)
    forward = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    left = np.array([-math.sin(yaw), math.cos(yaw), 0.0])
    up = np.array([0.0, 0.0, 1.0])
    length = max(0.16, scale_m * 0.55)
    shaft = max(0.004, scale_m * 0.015)
    head_radius = max(0.012, scale_m * 0.045)
    head_length = max(0.025, scale_m * 0.09)

    return [
        make_arrow(
            tuple(position),
            tuple(position + forward * length),
            shaft_radius=shaft,
            head_radius=head_radius,
            head_length=head_length,
            color=(1.0, 0.15, 0.15),
        ),
        make_arrow(
            tuple(position),
            tuple(position + left * length),
            shaft_radius=shaft,
            head_radius=head_radius,
            head_length=head_length,
            color=(0.15, 1.0, 0.15),
        ),
        make_arrow(
            tuple(position),
            tuple(position + up * length),
            shaft_radius=shaft,
            head_radius=head_radius,
            head_length=head_length,
            color=(0.15, 0.35, 1.0),
        ),
    ]


def _heading_part(
    position: np.ndarray,
    yaw_deg: float,
    scale_m: float,
    color: List[float],
) -> Any:
    yaw = math.radians(yaw_deg)
    forward = np.array([math.cos(yaw), math.sin(yaw), 0.0])
    start = np.asarray(position, dtype=np.float64).copy()
    start[2] += 0.025
    length = max(0.22, scale_m * 0.72)
    return make_arrow(
        tuple(start),
        tuple(start + forward * length),
        shaft_radius=max(0.005, scale_m * 0.018),
        head_radius=max(0.016, scale_m * 0.055),
        head_length=max(0.035, scale_m * 0.11),
        color=tuple(color),
    )


def _effective_render(
    waypoint: Dict[str, Any],
    params: Dict[str, Any],
) -> Dict[str, Any]:
    render = waypoint.get("render", {})
    render = render if isinstance(render, dict) else {}
    return {
        "mode": render.get("mode", params["default_mode"]),
        "scale_m": float(render.get("scale_m", params["default_scale_m"])),
        "icon_height_m": float(
            render.get("icon_height_m", params["default_icon_height_m"])
        ),
        "marker": render.get("marker", params["default_marker"]),
        "show_heading": bool(
            render.get("show_heading", params["default_show_heading"])
        ),
    }


def _icon_object(
    waypoint: Dict[str, Any],
    mode: str,
    position: np.ndarray,
    yaw_deg: float,
    scale_m: float,
    icon_height_m: float,
    ctx: Any,
) -> Optional[SceneObject]:
    if mode == "marker":
        return None

    emoji_path = _resolve_emoji_path(waypoint, _openmoji_root(ctx))
    if emoji_path is None:
        if waypoint.get("emoji") or waypoint.get("render", {}).get("emoji_file"):
            _warn(
                ctx,
                "Waypoint {!r} emoji asset was not found; showing pose geometry only.".format(
                    waypoint["id"]
                ),
            )
        return None

    texture = _load_texture(emoji_path)
    if texture is None:
        _warn(
            ctx,
            "Waypoint {!r} emoji could not be decoded; showing pose geometry only.".format(
                waypoint["id"]
            ),
        )
        return None

    if mode == "floor":
        geometry = _floor_icon(position, yaw_deg, scale_m)
    else:
        yaw = math.radians(yaw_deg)
        normal = np.array([math.cos(yaw), math.sin(yaw), 0.0])
        if mode == "camera_billboard":
            camera = getattr(ctx, "camera_world_pos", None)
            if camera is not None:
                normal = np.asarray(camera, dtype=np.float64) - position
                normal[2] = 0.0
        geometry = _upright_icon(
            position,
            normal,
            scale_m,
            icon_height_m,
        )

    return SceneObject(
        name="waypoint:{}:emoji".format(waypoint["id"]),
        kind="mesh",
        geometry=geometry,
        render_visible=True,
        raycast_visible=False,
        shader="defaultUnlit",
        albedo_image=texture,
        base_color_rgba=(1.0, 1.0, 1.0, 1.0),
        has_alpha=True,
    )


def build(params: Dict[str, Any], ctx: Any) -> Optional[List[SceneObject]]:
    """
    Render all enabled records from my shared waypoint registry.

    Args:
        params: Layer-wide rendering defaults from the mind palace.
        ctx: Chora context containing my world frame and virtual camera.

    Returns:
        Separate textured and pose-geometry objects for each waypoint, or None.

    Note to self:
        I intentionally disappear outside the map frame. Drawing a map pose in
        odom coordinates would look plausible while being dangerously wrong.
    """
    if not _HAS_O3D:
        return None

    if getattr(ctx, "world_frame", "") != "map":
        _warn(
            ctx,
            "Waypoints hidden because Chora's active world frame is not 'map'.",
        )
        return None

    try:
        import logos

        records = logos.waypoints.list()
    except Exception as exc:
        _warn(ctx, "Waypoint registry unavailable: {}".format(exc))
        return None

    objects: List[SceneObject] = []
    marker_color = [float(value) for value in params["marker_color"]]

    for waypoint in records:
        render = _effective_render(waypoint, params)
        mode = render["mode"]
        scale_m = render["scale_m"]
        icon_height_m = render["icon_height_m"]
        position = np.asarray(waypoint["pose"]["position"], dtype=np.float64)
        yaw_deg = float(waypoint["pose"]["rpy_deg"][2])

        icon = _icon_object(
            waypoint,
            mode,
            position,
            yaw_deg,
            scale_m,
            icon_height_m,
            ctx,
        )
        if icon is not None:
            objects.append(icon)

        marker_parts: List[Any] = []
        if render["marker"] == "pin":
            marker_parts.extend(_pin_parts(position, scale_m, marker_color))
        elif render["marker"] == "axes":
            marker_parts.extend(_axes_parts(position, yaw_deg, scale_m))

        if render["show_heading"]:
            marker_parts.append(
                _heading_part(position, yaw_deg, scale_m, marker_color)
            )

        marker_mesh = _combine_meshes(marker_parts)
        if marker_mesh is not None:
            objects.append(SceneObject(
                name="waypoint:{}:pose".format(waypoint["id"]),
                kind="mesh",
                geometry=marker_mesh,
                render_visible=True,
                raycast_visible=False,
                shader="defaultUnlit",
            ))

    return objects or None
