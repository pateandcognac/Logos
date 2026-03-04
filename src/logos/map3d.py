# src/logos/map3d.py
"""
My 'mind palace.' A virtual 3D environment for advanced spatial reasoning.

This module provides the tools to render a 3D scene of my environment from
a virtual camera's perspective. The scene is constructed from the ROS map,
my live Astra point cloud, and a 3D model of myself.

The core workflow is a two-step process:
1.  `render()`: Create a 2D image of the 3D scene. This returns a `RenderResult`
    object, which is like a `vision.CaptureResult` for this virtual space.
2.  `raycast()`: Use the `RenderResult` to project a 2D pixel from the
    rendered image back into the 3D world, giving me an actionable
    map coordinate.

# TODO: Document phantasmata, and a how-to.

This allows me to visually plan paths, understand spatial relationships, and
select navigation goals in a way that transcends my physical sensors.
"""
# VERY Important: this code is specific to **Open3D *0.13.0***
# Open3D 0.13 / Filament gotchas (read before "refactoring"):
# - OffscreenRenderer is thread-affine (single OS thread for all renderer ops).
# - Prefer rendering.Material for OffscreenRenderer; MaterialRecord snippets online
#   often apply to GUI draw()/O3DVisualizer flows and can crash here.
# - Transparency: use base_color RGBA + has_alpha=True on defaultUnlit/defaultLit.
#   Do NOT assume newer "*Transparency" shader strings exist or are compatible in 0.13.

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import os
import time
import math
import threading
import queue
import importlib
import importlib.util
import sys
import uuid
import traceback
import numpy as np

# YAML loader for mind_palace config
try:
    from ruamel.yaml import YAML
    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False

try:
    import rospy
    import tf2_ros
    import message_filters
    from sensor_msgs.msg import Image, PointCloud2, CameraInfo
    from nav_msgs.msg import OccupancyGrid
    from geometry_msgs.msg import PointStamped
    from cv_bridge import CvBridge
    import sensor_msgs.point_cloud2 as pc2
    import tf2_geometry_msgs
    _HAS_ROS = True
except Exception:
    _HAS_ROS = False

try:
    import open3d as o3d
    import open3d.visualization.rendering as rendering
    _HAS_O3D = True
except Exception:
    _HAS_O3D = False

# Open3D 0.13 supports both Material and MaterialRecord, but Open3DScene.add_geometry
# is typed for rendering.Material in 0.13 docs. We keep Material as the primary path
# because it matches what's running on the robot today.
try:
    from open3d.visualization.rendering import MaterialRecord  # type: ignore
    _HAS_MAT_RECORD = True
except Exception:
    MaterialRecord = None  # type: ignore
    _HAS_MAT_RECORD = False

try:
    import cv2
    _HAS_CV2 = True
except Exception:
    _HAS_CV2 = False

# ---- Optional Logos imports (kept soft so module can be introspected) ----

try:
    from logos.core import api_call, Verbosity, check_for_interrupt
except Exception:  # pragma: no cover
    def api_call(*_args, **_kwargs):  # type: ignore
        def _wrap(fn):
            return fn
        return _wrap

    class Verbosity:  # type: ignore
        ACK = 1
        DEBUG = 3

    def check_for_interrupt():  # type: ignore
        return

try:
    from logos import ros as logos_ros
except Exception:  # pragma: no cover
    logos_ros = None

# HUD system is now in vision.py for reuse across camera and map3d rendering
try:
    from logos.vision import (
        HudElement, HUD_ANCHORS, overlay_hud,
        HUD_FONT_SIMPLEX, HUD_FONT_PLAIN, HUD_FONT_DUPLEX,
        HUD_FONT_SMALL, HUD_FONT_MONO,
    )
    _HAS_VISION_HUD = True
except ImportError:
    _HAS_VISION_HUD = False
    # Fallback definitions below if vision.py not available

try:
    import ros_numpy
    _HAS_ROS_NUMPY = True
except Exception:
    ros_numpy = None  # type: ignore
    _HAS_ROS_NUMPY = False


# --------------------------- Data Structures ---------------------------

@dataclass
class RaycastHit:
    """Result of raycasting a pixel against a scene snapshot."""
    hit: str  # "astra_cloud" | "floor" | "robot" | "object:<name>" | "infinity"
    world_point: Tuple[float, float, float]
    distance_m: float
    floor_state: Optional[str] = None  # "map_open" | "map_occupied" | "unmapped"
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SceneObject:
    """An object that can be rendered and/or raycasted."""
    name: str
    kind: str  # "mesh" or "pointcloud"
    geometry: Any  # o3d.geometry.TriangleMesh or o3d.geometry.PointCloud
    render_visible: bool = True
    raycast_visible: bool = True
    costmap_affects: bool = False  # placeholder for future
    shader: str = "defaultLit"  # "defaultLit" or "defaultUnlit"
    point_size: float = 3.0  # only used for pointcloud rendering


@dataclass
class MapSnapshot:
    """
    Minimal map state needed for floor semantics and texture snapshotting.

    We store numpy occupancy and the grid metadata we need to index into it.
    Keeping this inside the render snapshot makes later raycasts agree with
    what the robot actually saw when the image was rendered.
    """
    stamp_sec: float
    resolution: float
    origin_x: float
    origin_y: float
    width: int
    height: int
    occ: np.ndarray  # (H, W) int16
    open_max: int = 25
    occupied_min: int = 75
    unknown_val: int = -1


@dataclass
class MeshSnapshot:
    """
    Mesh data frozen into numpy arrays for stable ray intersections.
    """
    vertices: np.ndarray  # (V, 3) float32
    triangles: np.ndarray  # (T, 3) int32


@dataclass
class ObjectSnapshot:
    """
    Frozen raycast target for registered objects.

    For pointclouds: points is (N, 3) float32.
    For meshes: mesh is MeshSnapshot.
    """
    name: str
    kind: str  # "mesh" or "pointcloud"
    points: Optional[np.ndarray] = None
    mesh: Optional[MeshSnapshot] = None


@dataclass
class SceneSnapshot:
    """Self-contained snapshot of what was rendered, sufficient for later raycasts."""
    render_id: str
    timestamp: float
    resolution: Tuple[int, int]  # (height, width)
    camera_world_pos: np.ndarray  # shape (3,)
    look_at_world_pos: np.ndarray  # shape (3,)
    view_matrix: np.ndarray  # 4x4
    projection_matrix: np.ndarray  # 4x4
    ray_infinity_distance_m: float = 50.0

    # Ray targets:
    astra_points_map: Optional[np.ndarray] = None  # (N, 3) float32 in world frame
    robot_mesh: Optional[MeshSnapshot] = None
    objects: List[ObjectSnapshot] = field(default_factory=list)

    # Map semantics:
    map_snapshot: Optional[MapSnapshot] = None


@dataclass
class RenderResult:
    """
    CaptureResult-shaped return for mind-palace rendering.
    image is BGR uint8 for consistency with the rest of Logos vision tooling.
    """
    image: np.ndarray
    source: str = "map3d"
    timestamp: float = 0.0
    resolution: Tuple[int, int] = (0, 0)
    photo_id: Optional[str] = None
    path: Optional[str] = None
    pose: Optional[Dict[str, float]] = None
    meta: Optional[Dict[str, Any]] = None

    def save(self, view: bool = False, path: Optional[str] = None) -> str:
        if self.path is None:
            import cv2
            import os

            # meta is optional because RenderResult is a general-purpose container.
            # Making it a dict on-demand avoids surprising AttributeErrors.
            self.meta = self.meta or {}

            self.photo_id = self.meta.get("render_id", uuid.uuid4().hex[:12])
            save_dir = "artifacts/map3d"
            os.makedirs(save_dir, exist_ok=True)
            self.path = path or os.path.join(save_dir, f"{self.photo_id}.png")
            cv2.imwrite(self.path, self.image)

        if view:
            self.view()
        return self.path

    def view(self) -> None:
        if self.path is None:
            self.save()
        print(f'<file path="{self.path}">Chora\n</file>')


# HUD system: prefer imports from vision.py; fallback definitions here
# if vision.py is not available (for standalone testing)
if not _HAS_VISION_HUD:
    # Named anchor positions for HUD elements. Elements sharing an anchor
    # are stacked vertically in priority order (lower = closer to anchor edge).
    HUD_ANCHORS = (
        "top_left", "top_center", "top_right",
        "bottom_left", "bottom_center", "bottom_right",
    )

    # OpenCV font constants (so callers don't need to import cv2 themselves)
    HUD_FONT_SIMPLEX = 0        # cv2.FONT_HERSHEY_SIMPLEX
    HUD_FONT_PLAIN = 1          # cv2.FONT_HERSHEY_PLAIN
    HUD_FONT_DUPLEX = 2         # cv2.FONT_HERSHEY_DUPLEX
    HUD_FONT_SMALL = 6          # cv2.FONT_HERSHEY_COMPLEX_SMALL
    HUD_FONT_MONO = 7           # cv2.FONT_HERSHEY_SCRIPT_SIMPLEX (not mono)

    @dataclass
    class HudElement:
        """
        A single text element to overlay on a rendered image.

        Positioning uses named anchors (see HUD_ANCHORS). Multiple elements
        at the same anchor are stacked vertically, sorted by priority (lower
        values render closer to the anchor edge, i.e. top for top_*, bottom
        for bottom_*).

        Colors are BGR uint8 tuples for direct OpenCV compatibility.
        """
        text: str
        anchor: str = "top_left"
        color: Tuple[int, int, int] = (255, 255, 255)  # BGR white
        bg_color: Optional[Tuple[int, int, int]] = (0, 0, 0)  # BGR; None = no bg
        bg_alpha: float = 0.4  # 0.0 = fully transparent bg, 1.0 = opaque
        font_scale: float = 0.45
        thickness: int = 1
        font: int = 0  # cv2.FONT_HERSHEY_SIMPLEX
        margin_px: int = 8  # padding from image edge and between stacked elements
        priority: int = 0  # lower = closer to anchor edge


# --------------------------- Math Helpers ---------------------------

def _quat_to_rot_matrix(qx: float, qy: float, qz: float, qw: float) -> np.ndarray:
    """Quaternion (x,y,z,w) to 3x3 rotation matrix."""
    n = math.sqrt(qx * qx + qy * qy + qz * qz + qw * qw)
    if n == 0.0:
        return np.eye(3)
    qx, qy, qz, qw = qx / n, qy / n, qz / n, qw / n

    xx = qx * qx
    yy = qy * qy
    zz = qz * qz
    xy = qx * qy
    xz = qx * qz
    yz = qy * qz
    wx = qw * qx
    wy = qw * qy
    wz = qw * qz

    return np.array([
        [1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz),       2.0 * (xz + wy)],
        [2.0 * (xy + wz),       1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)],
        [2.0 * (xz - wy),       2.0 * (yz + wx),       1.0 - 2.0 * (xx + yy)],
    ], dtype=np.float64)


def _normalize_norm1000(val: float) -> float:
    """Clamp 0..1000 and map 1000 exactly to the last pixel (not width)."""
    if math.isnan(val):
        return 0.0
    return max(0.0, min(1000.0, float(val)))


def _norm1000_to_pixel(norm_0_1000: float, size_px: int) -> float:
    """
    Convert normalized [0..1000] to pixel coordinate in [0..size-1].
    1000 maps to size-1.
    """
    n = _normalize_norm1000(norm_0_1000)
    if size_px <= 1:
        return 0.0
    return (n / 1000.0) * float(size_px - 1)


def _euler_rpy_deg_to_rot_matrix(
    roll: float,
    pitch: float,
    yaw: float,
) -> np.ndarray:
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


def _as_4x4(m: Any) -> np.ndarray:
    """
    Defensive conversion for camera matrices.

    Open3D 0.13 returns float32[4,4] for get_view_matrix/get_projection_matrix,
    but this keeps the unprojection path robust if an API ever hands us a flat
    16-array or a list-like.
    """
    a = np.asarray(m, dtype=np.float64)
    if a.shape == (16,):
        a = a.reshape((4, 4))
    if a.shape != (4, 4):
        raise ValueError(f"Expected 4x4 matrix, got {a.shape}")
    return a


# --------------------------- Core Map3d System ---------------------------

class Map3d:
    """
    Stateful renderer + raycaster with persistent ROS subscriptions.
    """

    def __init__(
        self,
        rgb_image_topic: str = "/camera/rgb/image_raw",
        rgb_info_topic: str = "/camera/rgb/camera_info",
        points_topic: str = "/camera/depth_registered/points",
        map_topic: str = "/map",
        base_frame: str = "base_footprint",
        map_frame: str = "map",
    ):
        if not _HAS_ROS:
            raise RuntimeError("ROS is not available (rospy imports failed).")
        if not _HAS_O3D:
            raise RuntimeError("Open3D is not available (open3d imports failed).")

        if not rospy.core.is_initialized():
            rospy.init_node("logos_map3d", anonymous=True, disable_signals=True)

        self.bridge = CvBridge()

        self.rgb_image_topic = rgb_image_topic
        self.rgb_info_topic = rgb_info_topic
        self.points_topic = points_topic
        self.map_topic = map_topic
        self.base_frame = base_frame
        self.map_frame = map_frame

        self._tf_buffer = None
        self._tf_listener = None

        # Latest synchronized camera triple
        self._frame_lock = threading.Lock()
        self._latest_pc: Optional[PointCloud2] = None
        self._latest_rgb: Optional[Image] = None
        self._latest_info: Optional[CameraInfo] = None
        self._latest_frame_time: float = 0.0
        self._frame_event = threading.Event()

        # Camera subscription lifecycle (on-demand)
        self._camera_subs_lock = threading.Lock()
        self._camera_subs_active = False
        self._pc_sub = None
        self._rgb_sub = None
        self._info_sub = None
        self._sync = None

        # Occupancy grid + cached floor mesh
        self._map_lock = threading.Lock()
        self._occupancy_grid: Optional[OccupancyGrid] = None
        self._occupancy_np: Optional[np.ndarray] = None  # (H, W) int16

        # Floor visual cache (textured plane)
        self._floor_visual_mesh: Optional[o3d.geometry.TriangleMesh] = None
        self._floor_visual_mat: Any = None
        self._floor_visual_stamp: Optional[rospy.Time] = None
        self._floor_visual_dims: Optional[Tuple[int, int]] = None  # (w, h)

        # Render snapshot cache — bounded LRU via OrderedDict
        self._renders: OrderedDict[str, SceneSnapshot] = OrderedDict()
        self._renders_lock = threading.Lock()
        self._renders_max: int = 10  # keep last N snapshots

        # Objects (legacy manual object management)
        self._objects_lock = threading.Lock()
        self._objects: Dict[str, SceneObject] = {}

        # ---- Phantasmata System ----
        # Phantasma modules (loaded Python modules, keyed by module name)
        self._phantasma_modules: Dict[str, Any] = {}
        self._phantasma_modules_lock = threading.Lock()

        # Instance configurations from mind_palace.yaml + runtime additions
        self._instances: Dict[str, Dict[str, Any]] = {}
        self._instances_lock = threading.Lock()

        # Cached built geometry per instance (keyed by instance name)
        self._instance_cache: Dict[str, List[SceneObject]] = {}
        self._instance_cache_lock = threading.Lock()

        # Configuration paths (can be overridden via logos.config.map3d)
        # self._phantasmata_dir: str = "src/logos/phantasmata"
        # self._mind_palace_path: str = "config/mind_palace_00.yaml"

        # Try to read paths and FOV from logos.config.merged.map3d
        map3d_config: Dict[str, Any] = {}
        default_fov_horz_deg = 63.0
        default_fov_axis = "horizontal"

        try:
            import logos
            map3d_config = logos.config.merged.get("map3d", {})

            if "phantasmata_dir" in map3d_config:
                self._phantasmata_dir = map3d_config["phantasmata_dir"]
            if "chora_config" in map3d_config:
                self._mind_palace_path = f"config/{map3d_config['chora_config']}"

            # --- FOV: new style ---
            cfg_fov_deg = map3d_config.get("fov_deg")
            cfg_fov_axis = map3d_config.get("fov_axis")

            # --- FOV: legacy styles ---
            cfg_fov_h = map3d_config.get("fov_horz_deg")
            cfg_fov_v = map3d_config.get("fov_vert_deg")

            chosen_fov_deg = None
            chosen_axis = None

            # Priority 1: explicit new-style scalar + axis
            if cfg_fov_deg is not None:
                chosen_fov_deg = float(cfg_fov_deg)
                if cfg_fov_axis is not None:
                    chosen_axis = str(cfg_fov_axis).lower()
                else:
                    chosen_axis = "horizontal"

            # Priority 2: legacy split (pick one)
            elif cfg_fov_h is not None or cfg_fov_v is not None:
                if cfg_fov_h is not None:
                    chosen_fov_deg = float(cfg_fov_h)
                    chosen_axis = "horizontal"
                    if cfg_fov_v is not None:
                        print(
                            "[map3d] WARN: Both fov_horz_deg and fov_vert_deg are set in config; "
                            "map3d now uses a single FOV. Using fov_horz_deg and ignoring fov_vert_deg."
                        )
                else:
                    chosen_fov_deg = float(cfg_fov_v)
                    chosen_axis = "vertical"

            if chosen_fov_deg is not None:
                default_fov_deg = chosen_fov_deg
            if chosen_axis is not None:
                default_fov_axis = chosen_axis

        except Exception:
            pass

        # Load mind palace configuration if it exists
        self._load_mind_palace()

        # Per-render warning accumulator (cleared at start of each render).
        self._render_warnings: List[str] = []
        self._render_warnings_lock = threading.Lock()

        # Active world frame: tracks what TF frame we're using for the current render.
        self._active_world_frame: Optional[str] = None

        # Settings
        self.settings = {
            "voxel_downsample": False,
            "voxel_size": 0.035,
            "stat_outlier_removal": True,
            "sor_neighbors": 50,
            "sor_std_ratio": 2.0,
            "point_hit_radius": 0.05,        # meters
            "ray_infinity_distance_m": 50.0,
            "render_point_size": 3.0,
            "fov_deg": float(default_fov_horz_deg),
            "fov_axis": "horizontal",              

            # Point cloud display
            "cloud_density": 1.0,             # 0.0-1.0, fraction of points to keep
            "cloud_opacity": 1.0,             # 0.0-1.0, vertex color blend toward bg
            "cloud_bg_color": [0.1, 0.1, 0.1],  # scene bg color for opacity blending
            "cloud_alpha": 1.0,  # 0..1 (1 = opaque) # Real transparency (Filament material alpha)

            # Laser scan visualization
            #
            # The depthimage_to_laserscan nodelet effectively samples around the
            # vertical center row of the depth image. Instead of thinking in
            # world-space meters, we emulate that by recoloring points whose
            # projected pixel v lies near the image center. This keeps the mental
            # model aligned with what /scan really is.
            "laser_scan_show": False,
            "laser_scan_center_band_px": 1,       # +/- around center row
            "laser_scan_color": [1.0, 0.0, 0.0],  # RGB red in [0,1]
        }

        # Open3D 0.13 + Filament has HARD thread affinity:
        # the OffscreenRenderer/Filament backend must be created + used from
        # one single OS thread for the lifetime of the renderer.
        #
        # If you touch renderer.scene / add_geometry / render_to_image from
        # multiple threads, you will eventually get native crashes or Filament
        # "PreconditionPanic" aborts.
        #
        # Therefore: ALL rendering work is marshalled onto _render_thread via
        # _run_on_render_thread().
        self._render_task_queue: queue.Queue = queue.Queue()
        self._render_thread = threading.Thread(
            target=self._render_worker, daemon=True, name="map3d-render"
        )
        self._render_thread.start()

        # Renderer cache (keyed by resolution, managed on render thread only)
        self._renderers: Dict[Tuple[int, int], rendering.OffscreenRenderer] = {}

        self._start_map_subscriber()
        # Camera subscribers are started on-demand inside render()

    # ---------------- ROS plumbing ----------------

    def _get_tf_buffer(self):
        if logos_ros is not None and hasattr(logos_ros, "get_tf_buffer"):
            return logos_ros.get_tf_buffer()

        if self._tf_buffer is None:
            self._tf_buffer = tf2_ros.Buffer()
            self._tf_listener = tf2_ros.TransformListener(self._tf_buffer)
        return self._tf_buffer

    def _start_map_subscriber(self) -> None:
        self._map_sub = rospy.Subscriber(
            self.map_topic,
            OccupancyGrid,
            self._map_callback,
            queue_size=1,
        )

    def _start_camera_subscribers(self) -> None:
        """
        Start the synchronized camera triple subscribers.

        Subscribing to PointCloud2 is expensive even if callbacks are light,
        because deserialization happens before the callback.
        """
        # Subscribing to PointCloud2 is expensive because ROS deserializes the message
        # before your callback runs. We only subscribe long enough to grab ONE synced
        # triple, then immediately unsubscribe to reduce CPU load + latency jitter.
        # This might lead to occasional timeouts but it is worth it.
        # TODO: handle timeouts gracefully
        with self._camera_subs_lock:
            if self._camera_subs_active:
                return

            # Clear *before* subscribing so the next set() corresponds to new data.
            self._frame_event.clear()

            self._pc_sub = message_filters.Subscriber(self.points_topic, PointCloud2, queue_size=1)
            self._rgb_sub = message_filters.Subscriber(self.rgb_image_topic, Image, queue_size=1)
            self._info_sub = message_filters.Subscriber(self.rgb_info_topic, CameraInfo, queue_size=1)

            self._sync = message_filters.ApproximateTimeSynchronizer(
                [self._pc_sub, self._rgb_sub, self._info_sub],
                queue_size=2,  # keep this small; clouds are big
                slop=0.2,
            )
            self._sync.registerCallback(self._camera_sync_callback)

            self._camera_subs_active = True

    def _stop_camera_subscribers(self) -> None:
        """Stop camera subscribers to eliminate background deserialization load."""
        with self._camera_subs_lock:
            if not self._camera_subs_active:
                return

            # message_filters.Subscriber wraps rospy.Subscriber in .sub
            for sub in (self._pc_sub, self._rgb_sub, self._info_sub):
                try:
                    if sub is not None and hasattr(sub, "sub") and sub.sub is not None:
                        sub.sub.unregister()
                except Exception:
                    pass

            self._pc_sub = None
            self._rgb_sub = None
            self._info_sub = None
            self._sync = None
            self._camera_subs_active = False

    def _camera_sync_callback(self, pc_msg: PointCloud2, rgb_msg: Image, info_msg: CameraInfo) -> None:
        with self._frame_lock:
            self._latest_pc = pc_msg
            self._latest_rgb = rgb_msg
            self._latest_info = info_msg
            try:
                self._latest_frame_time = pc_msg.header.stamp.to_sec()
            except Exception:
                self._latest_frame_time = time.time()
        self._frame_event.set()

    def _map_callback(self, msg: OccupancyGrid) -> None:
        with self._map_lock:
            self._occupancy_grid = msg
            try:
                h, w = msg.info.height, msg.info.width
                self._occupancy_np = np.array(msg.data, dtype=np.int16).reshape((h, w))
            except Exception:
                self._occupancy_np = None

            # Invalidate floor visual cache
            self._floor_visual_mesh = None
            self._floor_visual_mat = None
            self._floor_visual_stamp = msg.header.stamp if hasattr(msg, "header") else None
            self._floor_visual_dims = None

    def _wait_for_frame(self, timeout_s: float = 6.0) -> bool:
        return self._frame_event.wait(timeout=timeout_s)

    # ---------------- Scene object management ----------------

    def register_object(self, obj: SceneObject) -> None:
        with self._objects_lock:
            self._objects[obj.name] = obj

    def remove_object(self, name: str) -> None:
        with self._objects_lock:
            self._objects.pop(name, None)

    def load_phantasma(self, name: str) -> None:
        """
        Minimal legacy loader (deprecated, use place() instead).
        Expects phantasmata/<name>.py to define build() -> SceneObject or List[SceneObject].
        """
        mod = importlib.import_module(f"phantasmata.{name}")
        if not hasattr(mod, "build"):
            raise ValueError(f"phantasmata.{name} has no build()")

        built = mod.build()
        if isinstance(built, list):
            for obj in built:
                self.register_object(obj)
        else:
            self.register_object(built)

    # ---------------- Phantasmata Lifecycle Manager ----------------

    def _load_mind_palace(self) -> None:
        """
        Load phantom instance configurations from mind_palace.yaml.

        This populates self._instances with the configuration for each
        placed phantasma. The actual geometry is built lazily on first render.
        """
        if not _HAS_YAML:
            return

        if not os.path.exists(self._mind_palace_path):
            return

        try:
            yaml = YAML()
            with open(self._mind_palace_path, 'r') as f:
                config = yaml.load(f) or {}

            instances = config.get('instances', {})
            if not isinstance(instances, dict):
                return

            with self._instances_lock:
                for name, instance_config in instances.items():
                    if isinstance(instance_config, dict):
                        self._instances[name] = dict(instance_config)

        except Exception as e:
            print(f"[map3d] Warning: Failed to load mind_palace.yaml: {e}")

    def _import_phantasma_module(self, module_name: str) -> Optional[Any]:
        """
        Import a phantasma module by name.

        Args:
            module_name: Name of the module (e.g., 'grid_overlay')

        Returns:
            The imported module, or None if import failed
        """
        with self._phantasma_modules_lock:
            # Return cached module if already loaded
            if module_name in self._phantasma_modules:
                return self._phantasma_modules[module_name]

        module_path = os.path.join(self._phantasmata_dir, f"{module_name}.py")

        if not os.path.exists(module_path):
            print(f"[map3d] Phantasma module not found: {module_path}")
            return None

        try:
            # Generate unique module name to avoid conflicts
            full_module_name = f"logos.phantasmata.{module_name}"

            # Load the module
            spec = importlib.util.spec_from_file_location(full_module_name, module_path)
            if spec is None or spec.loader is None:
                print(f"[map3d] Cannot load phantasma spec: {module_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[full_module_name] = module
            spec.loader.exec_module(module)

            # Validate required interface
            if not hasattr(module, 'SCHEMA'):
                print(f"[map3d] Phantasma {module_name} missing SCHEMA")
                return None
            if not hasattr(module, 'build'):
                print(f"[map3d] Phantasma {module_name} missing build()")
                return None

            # Cache and return
            with self._phantasma_modules_lock:
                self._phantasma_modules[module_name] = module
            return module

        except Exception as e:
            print(f"[map3d] Failed to import phantasma {module_name}: {e}")
            traceback.print_exc()
            return None

    def _build_phantasma_context(
        self,
        instance_name: str,
        instance_config: Dict[str, Any],
        map_snapshot: Optional[MapSnapshot] = None,
    ) -> Any:
        """
        Create a PhantasmaContext for a build() or hud() call.

        Args:
            instance_name: Name of the instance being built
            instance_config: Configuration dict for this instance
            map_snapshot: Current frozen map state

        Returns:
            PhantasmaContext instance
        """
        # Import PhantasmaContext from phantasmata module
        try:
            from logos.phantasmata.phantasma_convention import PhantasmaContext
        except ImportError:
            # Fallback: return a simple dict-like namespace
            class SimpleContext:
                def __init__(self, **kwargs):
                    for k, v in kwargs.items():
                        setattr(self, k, v)
            PhantasmaContext = SimpleContext

        # Get robot pose
        robot_pose = None
        try:
            if logos_ros is not None and hasattr(logos_ros, 'get_pose'):
                robot_pose = logos_ros.get_pose()
        except Exception:
            pass

        # Get logos.config if available
        config = {}
        try:
            import logos
            if hasattr(logos, 'config'):
                config = logos.config.to_dict() if hasattr(logos.config, 'to_dict') else {}
        except Exception:
            pass

        # Get REPL namespace if available
        ns = {}
        try:
            import logos
            if hasattr(logos, '_py_namespace'):
                ns = logos._py_namespace
        except Exception:
            pass

        return PhantasmaContext(
            config=config,
            ns=ns,
            tf_buffer=self._get_tf_buffer(),
            robot_pose=robot_pose,
            map_snapshot=map_snapshot,
            world_frame=self._get_world_frame(),
            instance_name=instance_name,
            instance_config=instance_config,
            render_timestamp=time.time(),
        )

    def _merge_params_with_schema(
        self,
        params: Dict[str, Any],
        schema: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge user params with schema defaults.

        Args:
            params: User-provided parameters
            schema: The phantasma's SCHEMA dict

        Returns:
            Merged parameters dict
        """
        merged = {}

        # Fill in schema defaults
        for key, spec in schema.items():
            if isinstance(spec, dict):
                merged[key] = spec.get('default')
            else:
                merged[key] = spec

        # Override with user params
        merged.update(params)
        return merged

    def _apply_pose_to_geometry(
        self,
        geometry: Any,
        pose_config: Optional[Dict[str, Any]],
    ) -> Any:
        """
        Apply pose transformation to Open3D geometry.

        Args:
            geometry: Open3D geometry object
            pose_config: Pose config with 'position' and/or 'rpy_deg'

        Returns:
            The transformed geometry (modified in-place)
        """
        if pose_config is None:
            return geometry

        position = pose_config.get('position')
        rpy_deg = pose_config.get('rpy_deg')

        if position is None and rpy_deg is None:
            return geometry

        # Build 4x4 transform matrix
        mat = np.eye(4, dtype=np.float64)

        if rpy_deg is not None:
            roll, pitch, yaw = rpy_deg
            mat[:3, :3] = _euler_rpy_deg_to_rot_matrix(roll, pitch, yaw)

        if position is not None:
            mat[:3, 3] = position

        geometry.transform(mat)
        return geometry

    def _build_phantasma_instance(
        self,
        instance_name: str,
        instance_config: Dict[str, Any],
        ctx: Any,
        force_rebuild: bool = False,
    ) -> Optional[List[SceneObject]]:
        """
        Build the geometry for a single phantasma instance.

        Args:
            instance_name: Name of the instance
            instance_config: Configuration dict
            ctx: PhantasmaContext for this build
            force_rebuild: If True, ignore cache

        Returns:
            List of SceneObject, or None if build failed
        """
        object_name = instance_config.get('object')
        if not object_name:
            return None

        # Import the module
        module = self._import_phantasma_module(object_name)
        if module is None:
            return None

        # Check if we need to rebuild
        is_dynamic = getattr(module, 'DYNAMIC', False)

        if not force_rebuild and not is_dynamic:
            with self._instance_cache_lock:
                if instance_name in self._instance_cache:
                    return self._instance_cache[instance_name]

        # For dynamic modules, check should_rebuild if present
        if is_dynamic and not force_rebuild:
            if hasattr(module, 'should_rebuild') and callable(module.should_rebuild):
                params = self._merge_params_with_schema(
                    instance_config.get('params', {}),
                    getattr(module, 'SCHEMA', {}),
                )
                try:
                    if not module.should_rebuild(params, ctx):
                        with self._instance_cache_lock:
                            if instance_name in self._instance_cache:
                                return self._instance_cache[instance_name]
                except Exception as e:
                    print(f"[map3d] should_rebuild() failed for {instance_name}: {e}")

        # Merge params with schema defaults
        schema = getattr(module, 'SCHEMA', {})
        params = self._merge_params_with_schema(
            instance_config.get('params', {}),
            schema,
        )

        # Call build()
        try:
            result = module.build(params, ctx)
        except Exception as e:
            print(f"[map3d] build() failed for {instance_name}: {e}")
            traceback.print_exc()
            return None

        if result is None:
            return None

        # Normalize to list
        if isinstance(result, list):
            objects = result
        else:
            objects = [result]

        # Apply instance-level settings and pose
        pose_config = instance_config.get('pose')
        render_visible = instance_config.get('render_visible', True)
        raycast_visible = instance_config.get('raycast_visible', True)
        shader = instance_config.get('shader', 'defaultLit')

        processed_objects = []
        for i, obj in enumerate(objects):
            if obj is None:
                continue

            # Replace __auto__ name with instance name
            if hasattr(obj, 'name') and obj.name == '__auto__':
                obj.name = f"{instance_name}_{i}" if len(objects) > 1 else instance_name

            # Apply pose transform to geometry
            if pose_config is not None and hasattr(obj, 'geometry'):
                self._apply_pose_to_geometry(obj.geometry, pose_config)

            # Override visibility and shader from instance config
            if hasattr(obj, 'render_visible'):
                obj.render_visible = render_visible
            if hasattr(obj, 'raycast_visible'):
                obj.raycast_visible = raycast_visible
            if hasattr(obj, 'shader'):
                obj.shader = shader

            processed_objects.append(obj)

        # Cache the result
        with self._instance_cache_lock:
            self._instance_cache[instance_name] = processed_objects

        return processed_objects

    def _collect_hud_contributions(
        self,
        map_snapshot: Optional[MapSnapshot] = None,
    ) -> List[HudElement]:
        """
        Collect HUD contributions from all phantasmata with hud() functions.

        Returns:
            List of HudElement from all phantasmata
        """
        hud_elements: List[HudElement] = []

        with self._instances_lock:
            instances_copy = dict(self._instances)

        for instance_name, instance_config in instances_copy.items():
            if not instance_config.get('render_visible', True):
                continue

            object_name = instance_config.get('object')
            if not object_name:
                continue

            module = self._import_phantasma_module(object_name)
            if module is None:
                continue

            if not hasattr(module, 'hud') or not callable(module.hud):
                continue

            # Build context and call hud()
            ctx = self._build_phantasma_context(
                instance_name, instance_config, map_snapshot
            )
            params = self._merge_params_with_schema(
                instance_config.get('params', {}),
                getattr(module, 'SCHEMA', {}),
            )

            try:
                elements = module.hud(params, ctx)
                if elements:
                    hud_elements.extend(elements)
            except Exception as e:
                print(f"[map3d] hud() failed for {instance_name}: {e}")

        return hud_elements

    # ---------------- Phantasmata Public API ----------------

    @api_call(default_verbosity=Verbosity.ACK)
    def place(
        self,
        name: str,
        object: str,
        pose: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        description: str = "",
        render_visible: bool = True,
        raycast_visible: bool = True,
        costmap_affects: bool = False,
        shader: str = "defaultLit",
        save_to_yaml: bool = False,
    ) -> None:
        """
        Place a new phantasma instance in my mind palace.

        Args:
            name: Unique identifier for this instance
            object: Name of the phantasma module (e.g., 'grid_overlay')
            pose: Position and orientation dict:
                  {'position': [x, y, z], 'rpy_deg': [roll, pitch, yaw]}
            params: Parameters to pass to build(), merged with SCHEMA defaults
            description: Human-readable description of this instance
            render_visible: Whether to show in rendered images
            raycast_visible: Whether hittable by raycast
            costmap_affects: Whether to inject into navigation costmap
            shader: Open3D shader to use ('defaultLit' or 'defaultUnlit')
            save_to_yaml: If True, persist to mind_palace.yaml

        Note to self:
            This is how I populate my virtual world. I can place furniture,
            waypoints, debug visualizations, or any phantasma I've defined.
            The instance persists until I remove it or restart.
        """
        instance_config = {
            'object': object,
            'description': description,
            'render_visible': render_visible,
            'raycast_visible': raycast_visible,
            'costmap_affects': costmap_affects,
            'shader': shader,
            'params': params or {},
        }

        if pose is not None:
            instance_config['pose'] = pose

        with self._instances_lock:
            self._instances[name] = instance_config

        # Clear any cached geometry for this instance
        with self._instance_cache_lock:
            self._instance_cache.pop(name, None)

        if save_to_yaml:
            self._save_mind_palace()

    @api_call(default_verbosity=Verbosity.ACK)
    def remove(self, name: str, save_to_yaml: bool = False) -> None:
        """
        Remove a phantasma instance from my mind palace.

        Args:
            name: Name of the instance to remove
            save_to_yaml: If True, persist the removal to mind_palace.yaml
        """
        # Call cleanup if the module has it
        with self._instances_lock:
            instance_config = self._instances.get(name)

        if instance_config:
            object_name = instance_config.get('object')
            if object_name:
                module = self._import_phantasma_module(object_name)
                if module and hasattr(module, 'cleanup') and callable(module.cleanup):
                    try:
                        ctx = self._build_phantasma_context(name, instance_config, None)
                        module.cleanup(ctx)
                    except Exception as e:
                        print(f"[map3d] cleanup() failed for {name}: {e}")

        with self._instances_lock:
            self._instances.pop(name, None)

        with self._instance_cache_lock:
            self._instance_cache.pop(name, None)

        if save_to_yaml:
            self._save_mind_palace()

    @api_call(default_verbosity=Verbosity.ACK)
    def update_instance(self, name: str, **param_overrides) -> None:
        """
        Update parameters for an existing phantasma instance.

        Args:
            name: Name of the instance
            **param_overrides: Parameter values to update
        """
        with self._instances_lock:
            if name not in self._instances:
                raise ValueError(f"Instance '{name}' not found")

            if 'params' not in self._instances[name]:
                self._instances[name]['params'] = {}

            self._instances[name]['params'].update(param_overrides)

        # Clear cache to trigger rebuild
        with self._instance_cache_lock:
            self._instance_cache.pop(name, None)

    @api_call(default_verbosity=Verbosity.ACK)
    def move_instance(
        self,
        name: str,
        position: Optional[List[float]] = None,
        rpy_deg: Optional[List[float]] = None,
    ) -> None:
        """
        Move a phantasma instance to a new pose.

        Args:
            name: Name of the instance
            position: New [x, y, z] position in meters
            rpy_deg: New [roll, pitch, yaw] in degrees
        """
        with self._instances_lock:
            if name not in self._instances:
                raise ValueError(f"Instance '{name}' not found")

            if 'pose' not in self._instances[name]:
                self._instances[name]['pose'] = {}

            if position is not None:
                self._instances[name]['pose']['position'] = list(position)
            if rpy_deg is not None:
                self._instances[name]['pose']['rpy_deg'] = list(rpy_deg)

        # Clear cache to trigger rebuild
        with self._instance_cache_lock:
            self._instance_cache.pop(name, None)

    @api_call(default_verbosity=Verbosity.ACK)
    def set_visible(
        self,
        name: str,
        render: Optional[bool] = None,
        raycast: Optional[bool] = None,
    ) -> None:
        """
        Toggle visibility settings for a phantasma instance.

        Args:
            name: Name of the instance
            render: If specified, set render_visible
            raycast: If specified, set raycast_visible
        """
        with self._instances_lock:
            if name not in self._instances:
                raise ValueError(f"Instance '{name}' not found")

            if render is not None:
                self._instances[name]['render_visible'] = render
            if raycast is not None:
                self._instances[name]['raycast_visible'] = raycast

    def list_instances(self) -> Dict[str, Dict[str, Any]]:
        """
        List all phantasma instances currently placed in my mind palace.

        Returns:
            Dict mapping instance names to their configuration summaries
        """
        with self._instances_lock:
            result = {}
            for name, config in self._instances.items():
                result[name] = {
                    'object': config.get('object'),
                    'description': config.get('description', ''),
                    'render_visible': config.get('render_visible', True),
                    'raycast_visible': config.get('raycast_visible', True),
                }
            return result

    def describe_instance(self, name: str) -> Dict[str, Any]:
        """
        Get the full configuration for a specific instance.

        Args:
            name: Name of the instance

        Returns:
            Full configuration dict
        """
        with self._instances_lock:
            if name not in self._instances:
                raise ValueError(f"Instance '{name}' not found")
            return dict(self._instances[name])

    def list_phantasmata(self) -> List[str]:
        """
        List all available phantasma modules.

        Returns:
            List of module names (e.g., ['grid_overlay', 'waypoints'])
        """
        if not os.path.isdir(self._phantasmata_dir):
            return []

        modules = []
        for filename in os.listdir(self._phantasmata_dir):
            if not filename.endswith('.py'):
                continue
            if filename.startswith('_'):
                continue
            if filename == 'phantasma_convention.py':
                continue
            modules.append(filename[:-3])

        return sorted(modules)

    def describe_phantasma(self, object_name: str) -> Dict[str, Any]:
        """
        Get information about a phantasma module.

        Args:
            object_name: Name of the phantasma module

        Returns:
            Dict with 'docstring', 'schema', 'dynamic', 'has_hud'
        """
        module = self._import_phantasma_module(object_name)
        if module is None:
            raise ValueError(f"Phantasma '{object_name}' not found or failed to import")

        return {
            'docstring': module.__doc__ or '',
            'schema': getattr(module, 'SCHEMA', {}),
            'dynamic': getattr(module, 'DYNAMIC', False),
            'has_hud': hasattr(module, 'hud') and callable(module.hud),
        }

    @api_call(default_verbosity=Verbosity.ACK)
    def reload_mind_palace(self) -> None:
        """
        Reload the mind_palace.yaml configuration.

        This clears all current instances and reloads from disk.
        Useful after manually editing the config file.
        """
        with self._instances_lock:
            self._instances.clear()

        with self._instance_cache_lock:
            self._instance_cache.clear()

        self._load_mind_palace()

    @api_call(default_verbosity=Verbosity.ACK)
    def rebuild(self, name: Optional[str] = None) -> None:
        """
        Force rebuild of phantasma geometry.

        Args:
            name: Specific instance to rebuild, or None for all instances
        """
        if name is not None:
            with self._instance_cache_lock:
                self._instance_cache.pop(name, None)
        else:
            with self._instance_cache_lock:
                self._instance_cache.clear()

    def _save_mind_palace(self) -> None:
        """
        Save current instances to mind_palace.yaml.
        """
        if not _HAS_YAML:
            print("[map3d] Cannot save: ruamel.yaml not available")
            return

        try:
            yaml = YAML()
            yaml.default_flow_style = False

            config = {'instances': {}}
            with self._instances_lock:
                for name, instance in self._instances.items():
                    config['instances'][name] = dict(instance)

            os.makedirs(os.path.dirname(self._mind_palace_path), exist_ok=True)
            with open(self._mind_palace_path, 'w') as f:
                yaml.dump(config, f)

        except Exception as e:
            print(f"[map3d] Failed to save mind_palace.yaml: {e}")

    # ---------------- Mesh/PCD preprocessing ----------------

    def _pc2_to_xyz_numpy(self, pc_msg: PointCloud2) -> np.ndarray:
        """
        Fast PointCloud2 -> (N, 3) float64 using ros_numpy.

        Returns empty array if no points.
        """
        if not _HAS_ROS_NUMPY or ros_numpy is None:
            # Fallback to the existing slow path (handled by caller)
            return np.empty((0, 3), dtype=np.float64)

        arr = ros_numpy.point_cloud2.pointcloud2_to_array(pc_msg)
        if arr.size == 0:
            return np.empty((0, 3), dtype=np.float64)

        x = np.asarray(arr["x"], dtype=np.float64).reshape(-1)
        y = np.asarray(arr["y"], dtype=np.float64).reshape(-1)
        z = np.asarray(arr["z"], dtype=np.float64).reshape(-1)

        xyz = np.column_stack((x, y, z))

        finite = np.isfinite(xyz).all(axis=1)
        xyz = xyz[finite]
        if xyz.size == 0:
            return xyz

        xyz = xyz[xyz[:, 2] > 0.0]
        return xyz

    def _preprocess_point_cloud(
        self,
        pcd: o3d.geometry.PointCloud,
        cloud_density: Optional[float] = None,
        cloud_opacity: Optional[float] = None,
        rng_seed: Optional[int] = None,
    ) -> o3d.geometry.PointCloud:
        """
        Post-process a map-frame point cloud for rendering.

        Applies (in order):
          1. Statistical outlier removal (if enabled)
          2. Voxel downsampling (legacy toggle)
          3. Deterministic density subsampling (stable debug behavior)
          4. Opacity blending (mix vertex colors toward scene background)
        """
        if not pcd.has_points():
            return pcd

        density = (
            cloud_density if cloud_density is not None
            else float(self.settings["cloud_density"])
        )
        opacity = (
            cloud_opacity if cloud_opacity is not None
            else float(self.settings["cloud_opacity"])
        )

        processed = o3d.geometry.PointCloud(pcd)

        # ---- 1. Outlier removal ----
        if self.settings["stat_outlier_removal"]:
            nn = int(self.settings["sor_neighbors"])
            if len(processed.points) > nn:
                processed, _ = processed.remove_statistical_outlier(
                    nb_neighbors=nn,
                    std_ratio=float(self.settings["sor_std_ratio"]),
                )

        # ---- 2. Voxel downsampling ----
        if self.settings["voxel_downsample"] and processed.has_points():
            processed = processed.voxel_down_sample(self.settings["voxel_size"])

        # ---- 3. Density subsampling ----
        #
        # A stable subsample keeps debugging sane. Using a per-frame seed gives
        # "same input frame => same subset" behavior, while still allowing the
        # subset to change over time as the scene changes.
        if 0.0 < density < 1.0 and len(processed.points) > 0:
            n_pts = len(processed.points)
            n_keep = max(1, int(n_pts * density))

            seed = int(rng_seed) if rng_seed is not None else 0
            rng = np.random.default_rng(seed=seed)

            indices = rng.choice(n_pts, size=n_keep, replace=False)
            indices.sort()
            processed = processed.select_by_index(indices.tolist())

        if not processed.has_points():
            return processed

        # Colors are required for pointcloud rendering paths that blend/annotate.
        if not processed.has_colors():
            processed.paint_uniform_color([0.8, 0.2, 0.2])

        # ---- 4. Opacity blending ----
        # NOTE: "cloud_opacity" here is NOT real alpha transparency.
        # It's a visual hack: blend per-point RGB toward the background color.
        # This works everywhere (even legacy visualizers) and avoids transparency
        # sorting artifacts, but it is not actual blending in the renderer.
        #
        # Real transparency (Filament) is handled in _render_scene via
        # material.base_color alpha + material.has_alpha.
        if opacity < 1.0:
            colors = np.asarray(processed.colors).copy()
            bg = np.array(self.settings["cloud_bg_color"], dtype=np.float64)
            colors = colors * opacity + bg * (1.0 - opacity)
            processed.colors = o3d.utility.Vector3dVector(colors)

        return processed

    def _transform_pcd_to_map(
        self,
        pcd: o3d.geometry.PointCloud,
        source_frame: str,
    ) -> Optional[o3d.geometry.PointCloud]:
        world_frame = self._get_world_frame()

        if not world_frame:
            return o3d.geometry.PointCloud(pcd)

        buf = self._get_tf_buffer()
        try:
            tfm = buf.lookup_transform(world_frame, source_frame, rospy.Time(0), rospy.Duration(0.5))
            t = tfm.transform.translation
            r = tfm.transform.rotation

            mat = np.eye(4, dtype=np.float64)
            mat[:3, :3] = _quat_to_rot_matrix(r.x, r.y, r.z, r.w)
            mat[:3, 3] = [t.x, t.y, t.z]

            pcd_t = o3d.geometry.PointCloud(pcd)
            pcd_t.transform(mat)
            return pcd_t
        except Exception:
            return None

    def _build_live_colored_pcd_map(
        self,
        pc_msg: PointCloud2,
        rgb_msg: Image,
        info_msg: CameraInfo,
        max_cloud_height_m: Optional[float] = None,
        cloud_density: Optional[float] = None,
        cloud_opacity: Optional[float] = None,
        laser_scan_show: Optional[bool] = None,
        laser_scan_center_band_px: Optional[int] = None,
        laser_scan_color: Optional[List[float]] = None,
    ) -> Optional[o3d.geometry.PointCloud]:
        """
        Build a colored point cloud in map frame from the synchronized camera
        triple using vectorized numpy operations.

        The registered depth topic (/camera/depth_registered/points) provides
        XYZ already aligned with the RGB intrinsics, so we project to pixel
        coords for color lookup via vectorized math.
        """
        check_for_interrupt()

        cv_bgr = self.bridge.imgmsg_to_cv2(rgb_msg, desired_encoding="bgr8")
        h_img, w_img = cv_bgr.shape[:2]
        fx, fy = float(info_msg.K[0]), float(info_msg.K[4])
        cx, cy = float(info_msg.K[2]), float(info_msg.K[5])

        show_scan = (
            laser_scan_show if laser_scan_show is not None
            else bool(self.settings["laser_scan_show"])
        )
        scan_band = (
            laser_scan_center_band_px if laser_scan_center_band_px is not None
            else int(self.settings["laser_scan_center_band_px"])
        )
        scan_rgb = (
            laser_scan_color if laser_scan_color is not None
            else list(self.settings["laser_scan_color"])
        )

        # ---- Extract XYZ from PointCloud2 (fast path: ros_numpy) ----
        xyz = self._pc2_to_xyz_numpy(pc_msg)

        # Fallback if ros_numpy unavailable or returned nothing
        if xyz.size == 0:
            xyz = np.array(
                list(pc2.read_points(pc_msg, field_names=("x", "y", "z"), skip_nans=True)),
                dtype=np.float64,
            )
            if xyz.size == 0:
                return None

            if xyz.ndim == 1 and xyz.dtype.names:
                xyz = np.column_stack([xyz[f] for f in ("x", "y", "z")])

            xyz = xyz[np.isfinite(xyz).all(axis=1)]
            xyz = xyz[xyz[:, 2] > 0.0]

        if xyz.shape[0] == 0:
            return None

        check_for_interrupt()

        # ---- Vectorized projection to pixel coordinates ----
        x_cam, y_cam, z_cam = xyz[:, 0], xyz[:, 1], xyz[:, 2]
        u = (fx * x_cam / z_cam + cx).astype(np.int32)
        v = (fy * y_cam / z_cam + cy).astype(np.int32)

        in_bounds = (u >= 0) & (u < w_img) & (v >= 0) & (v < h_img)
        xyz = xyz[in_bounds]
        u = u[in_bounds]
        v = v[in_bounds]

        if xyz.shape[0] == 0:
            return None

        # ---- Vectorized color sampling ----
        bgr = cv_bgr[v, u]                             # (N, 3) uint8
        rgb = bgr[:, ::-1].astype(np.float64) / 255.0  # RGB float [0,1]

        # ---- Emulate depthimage_to_laserscan sampling band ----
        #
        # The classic nodelet generates a scan from around the vertical center
        # of the depth image. Coloring those same pixels in our point cloud makes
        # "what /scan is" obvious without any frame math.
        if show_scan:
            center_row = h_img // 2
            lo = max(0, center_row - int(scan_band))
            hi = min(h_img - 1, center_row + int(scan_band))
            scan_mask = (v >= lo) & (v <= hi)
            if np.any(scan_mask):
                rgb[scan_mask] = np.asarray(scan_rgb, dtype=np.float64)

        check_for_interrupt()

        # ---- Build Open3D PointCloud (camera frame) ----
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(xyz)
        pcd.colors = o3d.utility.Vector3dVector(rgb)

        # ---- Transform to world frame ----
        pcd_map = self._transform_pcd_to_map(pcd, pc_msg.header.frame_id)
        if pcd_map is None or not pcd_map.has_points():
            return None

        # ---- Optional ceiling clip in world frame ----
        if max_cloud_height_m is not None:
            pts = np.asarray(pcd_map.points)
            keep = np.where(pts[:, 2] < float(max_cloud_height_m))[0]
            pcd_map = pcd_map.select_by_index(keep.tolist())

        # ---- Preprocessing: outlier removal, density, opacity ----
        #
        # Seed derives from the sensor timestamp, which makes subsampling stable
        # for a given input frame while still changing over time naturally.
        try:
            stamp_nsec = int(pc_msg.header.stamp.to_nsec())
        except Exception:
            stamp_nsec = int(time.time() * 1e9)
        seed = stamp_nsec & 0xFFFFFFFF

        return self._preprocess_point_cloud(
            pcd_map,
            cloud_density=cloud_density,
            cloud_opacity=cloud_opacity,
            rng_seed=seed,
        )

    # ---------------- Floor mesh + occupancy semantics ----------------

    def _floor_state_at_map_snapshot(self, x: float, y: float, ms: Optional[MapSnapshot]) -> str:
        if ms is None or ms.occ is None:
            return "unmapped"

        res = float(ms.resolution)
        origin_x = float(ms.origin_x)
        origin_y = float(ms.origin_y)
        w = int(ms.width)
        h = int(ms.height)

        j = int((x - origin_x) / res)
        i = int((y - origin_y) / res)

        if i < 0 or i >= h or j < 0 or j >= w:
            return "unmapped"

        val = int(ms.occ[i, j])
        if 0 <= val <= int(ms.open_max):
            return "map_open"
        if val >= int(ms.occupied_min):
            return "map_occupied"
        return "unmapped"

    def _build_occupancy_texture_rgb(
        self,
        occ: np.ndarray,
        open_max: int = 25,
        occupied_min: int = 75,
        unknown_val: int = -1,
        flip_y: bool = True,
    ) -> np.ndarray:
        """
        Convert occupancy array (H,W) into an RGB uint8 image (H,W,3).
        flip_y=True makes the texture align with +Y "up" in the world.
        """
        h, w = occ.shape[:2]
        img = np.empty((h, w, 3), dtype=np.uint8)

        open_rgb = np.array([230, 230, 230], dtype=np.uint8)
        occ_rgb = np.array([30, 30, 30], dtype=np.uint8)
        unk_rgb = np.array([128, 128, 128], dtype=np.uint8)

        unk_mask = (occ == unknown_val) | ((occ > open_max) & (occ < occupied_min))
        open_mask = (occ >= 0) & (occ <= open_max)
        occ_mask = (occ >= occupied_min)

        img[unk_mask] = unk_rgb
        img[open_mask] = open_rgb
        img[occ_mask] = occ_rgb

        if flip_y:
            img = np.flipud(img)

        return img

    def _make_floor_plane_with_uvs(
        self,
        origin_x: float,
        origin_y: float,
        width_cells: int,
        height_cells: int,
        res: float,
        z: float = 0.0,
    ) -> o3d.geometry.TriangleMesh:
        """
        Create a single quad covering the map extents with UVs.
        """
        w_m = float(width_cells) * float(res)
        h_m = float(height_cells) * float(res)

        x0 = float(origin_x)
        y0 = float(origin_y)
        x1 = x0 + w_m
        y1 = y0 + h_m

        vertices = np.array(
            [[x0, y0, z], [x1, y0, z], [x1, y1, z], [x0, y1, z]],
            dtype=np.float64,
        )
        triangles = np.array([[0, 1, 2], [0, 2, 3]], dtype=np.int32)
        uvs = np.array(
            [
                [0.0, 0.0], [1.0, 0.0], [1.0, 1.0],   # tri 0
                [0.0, 0.0], [1.0, 1.0], [0.0, 1.0],   # tri 1
            ],
            dtype=np.float64,
        )

        mesh = o3d.geometry.TriangleMesh()
        mesh.vertices = o3d.utility.Vector3dVector(vertices)
        mesh.triangles = o3d.utility.Vector3iVector(triangles)
        mesh.triangle_uvs = o3d.utility.Vector2dVector(uvs)
        mesh.compute_vertex_normals()
        return mesh

    def _make_unlit_texture_material(self, tex_rgb: np.ndarray) -> Any:
        """
        Open3D 0.13: OffscreenRenderer textures via rendering.Material.albedo_img.
        We provide RGBA to avoid edge-case channel handling.
        """
        tex_rgb = np.ascontiguousarray(tex_rgb.astype(np.uint8, copy=False))
        h, w = tex_rgb.shape[:2]
        alpha = np.full((h, w, 1), 255, dtype=np.uint8)
        tex_rgba = np.concatenate([tex_rgb, alpha], axis=2)

        tex_img = o3d.geometry.Image(tex_rgba)

        mat = rendering.Material()
        mat.shader = "defaultUnlit"

        # In 0.13, albedo_img exists on rendering.Material
        if hasattr(mat, "albedo_img"):
            mat.albedo_img = tex_img

        # base_color is the multiplier; keep it white so the texture is literal
        if hasattr(mat, "base_color"):
            mat.base_color = [1.0, 1.0, 1.0, 1.0]

        return mat

    def _get_floor_visual_cached(self) -> Tuple[o3d.geometry.TriangleMesh, Any]:
        """
        Return a (mesh, material) pair for a textured floor that matches the map.
        Cached; rebuilt only when the map changes.
        """
        with self._map_lock:
            grid = self._occupancy_grid
            occ = self._occupancy_np
            stamp = (
                grid.header.stamp if (grid is not None and hasattr(grid, "header")) else None
            )

            if (
                self._floor_visual_mesh is not None
                and self._floor_visual_mat is not None
                and self._floor_visual_stamp == stamp
            ):
                return self._floor_visual_mesh, self._floor_visual_mat

        # No map yet: fallback plane
        if grid is None or occ is None:
            plane = o3d.geometry.TriangleMesh.create_box(width=20.0, height=20.0, depth=0.01)
            plane.paint_uniform_color([0.3, 0.3, 0.3])
            plane.translate([-10.0, -10.0, -0.01])
            plane.compute_vertex_normals()

            mat = self._make_unlit_texture_material(
                np.full((2, 2, 3), 80, dtype=np.uint8)
            )
            with self._map_lock:
                self._floor_visual_mesh = plane
                self._floor_visual_mat = mat
                self._floor_visual_stamp = stamp
            return plane, mat

        width_cells = int(grid.info.width)
        height_cells = int(grid.info.height)
        res = float(grid.info.resolution)
        origin_x = float(grid.info.origin.position.x)
        origin_y = float(grid.info.origin.position.y)

        tex_rgb = self._build_occupancy_texture_rgb(occ=occ, flip_y=True)
        mesh = self._make_floor_plane_with_uvs(
            origin_x=origin_x,
            origin_y=origin_y,
            width_cells=width_cells,
            height_cells=height_cells,
            res=res,
            z=0.0,
        )

        mat = self._make_unlit_texture_material(tex_rgb)
        if mat is None:
            mesh.paint_uniform_color([0.35, 0.35, 0.35])
            mesh.compute_vertex_normals()

        with self._map_lock:
            self._floor_visual_mesh = mesh
            self._floor_visual_mat = mat
            self._floor_visual_stamp = stamp
            self._floor_visual_dims = (width_cells, height_cells)

        return mesh, mat

    def _make_map_snapshot(self) -> Optional[MapSnapshot]:
        """
        Freeze the current map into a compact, numpy-friendly snapshot.

        This avoids "rendered with one map, raycasted with a newer map" confusion.
        """
        with self._map_lock:
            grid = self._occupancy_grid
            occ = self._occupancy_np

            if grid is None or occ is None:
                return None

            try:
                stamp_sec = float(grid.header.stamp.to_sec())
            except Exception:
                stamp_sec = time.time()

            ms = MapSnapshot(
                stamp_sec=stamp_sec,
                resolution=float(grid.info.resolution),
                origin_x=float(grid.info.origin.position.x),
                origin_y=float(grid.info.origin.position.y),
                width=int(grid.info.width),
                height=int(grid.info.height),
                occ=np.array(occ, dtype=np.int16, copy=True),
            )
            return ms

    # ---------------- Robot model ----------------

    def _get_robot_transform_map(self) -> Optional[np.ndarray]:
        world_frame = self._get_world_frame()

        if not world_frame:
            return np.eye(4, dtype=np.float64)

        buf = self._get_tf_buffer()
        try:
            tfm = buf.lookup_transform(world_frame, self.base_frame, rospy.Time(0), rospy.Duration(0.3))
            t = tfm.transform.translation
            r = tfm.transform.rotation

            mat = np.eye(4, dtype=np.float64)
            mat[:3, :3] = _quat_to_rot_matrix(r.x, r.y, r.z, r.w)
            mat[:3, 3] = [t.x, t.y, t.z]
            return mat
        except Exception:
            return None

    def _create_robot_mesh_render_only(self) -> Optional[o3d.geometry.TriangleMesh]:
        """
        Build a robot mesh for rendering.

        I first try to use the self_model phantasma for my body representation.
        If that fails, I fall back to the legacy logos_mesh module.

        For raycasting, we freeze triangle/vertex arrays into MeshSnapshot to
        prevent future transforms (or rebuilds) from changing the past.
        """
        tfm = self._get_robot_transform_map()
        if tfm is None:
            return None

        # Try to build from self_model phantasma first
        if not hasattr(self, "_logos_base_mesh") or self._logos_base_mesh is None:
            mesh_built = False

            # Try self_model phantasma
            try:
                from logos.phantasmata.phantasma_convention import PhantasmaContext
                from logos.phantasmata import self_model

                # Build with default params
                schema = getattr(self_model, 'SCHEMA', {})
                params = {}
                for key, spec in schema.items():
                    if isinstance(spec, dict):
                        params[key] = spec.get('default')
                    else:
                        params[key] = spec

                # Create minimal context
                ctx = PhantasmaContext(
                    instance_name='self',
                    instance_config={'object': 'self_model'},
                )

                result = self_model.build(params, ctx)
                if result is not None and hasattr(result, 'geometry'):
                    self._logos_base_mesh = result.geometry
                    mesh_built = True
            except Exception as e:
                # Fallback will be used
                pass

            # Fallback to legacy logos_mesh
            if not mesh_built:
                try:
                    from Logos.marks_mess_sorry.logos_mesh import build_logos_mesh
                    self._logos_base_mesh = build_logos_mesh()
                except Exception:
                    return None

        if self._logos_base_mesh is None:
            return None

        robot = o3d.geometry.TriangleMesh(self._logos_base_mesh)
        robot.transform(tfm)
        robot.compute_vertex_normals()
        return robot

    # ---------------- Render warnings ----------------

    def _clear_render_warnings(self) -> None:
        with self._render_warnings_lock:
            self._render_warnings.clear()

    def _add_render_warning(self, msg: str) -> None:
        with self._render_warnings_lock:
            if msg not in self._render_warnings:
                self._render_warnings.append(msg)
                print(f"[map3d] WARN: {msg}")

    def _get_render_warnings(self) -> List[str]:
        with self._render_warnings_lock:
            return list(self._render_warnings)

    # ---------------- World-frame fallback ----------------

    def _resolve_world_frame(self) -> str:
        buf = self._get_tf_buffer()

        for candidate in [self.map_frame, "odom"]:
            try:
                buf.lookup_transform(
                    candidate, self.base_frame,
                    rospy.Time(0), rospy.Duration(0.3),
                )
                if candidate != self.map_frame:
                    self._add_render_warning(
                        f"Map frame '{self.map_frame}' unavailable — "
                        f"using '{candidate}'"
                    )
                self._active_world_frame = candidate
                return candidate
            except Exception:
                continue

        self._add_render_warning(
            "No TF frames available (map/odom) — rendering in base frame"
        )
        self._active_world_frame = ""
        return ""

    def _get_world_frame(self) -> str:
        if self._active_world_frame is not None:
            return self._active_world_frame
        return self.map_frame

    # ---------------- Camera targeting ----------------

    def _point_base_to_map(self, xyz_base: Tuple[float, float, float]) -> Optional[np.ndarray]:
        buf = self._get_tf_buffer()
        world_frame = self._get_world_frame()

        if not world_frame:
            return np.array(xyz_base, dtype=np.float64)

        pt = PointStamped()
        pt.header.stamp = rospy.Time(0)
        pt.point.x, pt.point.y, pt.point.z = xyz_base

        candidate_frames = [self.base_frame]
        if self.base_frame != "base_link":
            candidate_frames.append("base_link")
        if self.base_frame != "base_footprint":
            candidate_frames.append("base_footprint")

        last_err = None
        for frame in candidate_frames:
            pt.header.frame_id = frame
            try:
                tfm = buf.lookup_transform(world_frame, frame, rospy.Time(0), rospy.Duration(0.5))
                out = tf2_geometry_msgs.do_transform_point(pt, tfm)
                return np.array([out.point.x, out.point.y, out.point.z], dtype=np.float64)
            except Exception as e:
                last_err = e

        print(f"[map3d] TF point transform failed ({candidate_frames} -> {world_frame}): {last_err}")
        return None

    def _resolve_camera_and_lookat(
        self,
        camera_pos_relative: Optional[Tuple[float, float, float]],
        camera_pos_world: Optional[Tuple[float, float, float]],
        look_at_relative: Optional[Tuple[float, float, float]],
        look_at_world: Optional[Tuple[float, float, float]],
        rpy_deg: Optional[Tuple[float, float, float]],
        rot_matrix_3x3: Optional[np.ndarray],
        look_distance_m: float = 2.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Reduce all supported targeting modes to (camera_world_pos, look_at_world_pos)."""
        if camera_pos_world is not None:
            cam_world = np.array(camera_pos_world, dtype=np.float64)
        elif camera_pos_relative is not None:
            cam_world = self._point_base_to_map(camera_pos_relative)
            if cam_world is None:
                raise RuntimeError("TF failed: could not transform camera_pos_relative to map.")
        else:
            raise ValueError("Must supply camera_pos_relative or camera_pos_world.")

        if look_at_world is not None:
            return cam_world, np.array(look_at_world, dtype=np.float64)

        if look_at_relative is not None:
            look_world = self._point_base_to_map(look_at_relative)
            if look_world is None:
                raise RuntimeError("TF failed: could not transform look_at_relative to map.")
            return cam_world, look_world

        if rot_matrix_3x3 is not None:
            rot = np.array(rot_matrix_3x3, dtype=np.float64).reshape((3, 3))
        elif rpy_deg is not None:
            rot = _euler_rpy_deg_to_rot_matrix(*rpy_deg)
        else:
            raise ValueError("Must supply one of look_at_relative, look_at_world, rpy_deg, or rot_matrix_3x3.")

        forward = rot @ np.array([1.0, 0.0, 0.0], dtype=np.float64)
        forward_norm = np.linalg.norm(forward)
        if forward_norm < 1e-9:
            forward = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        else:
            forward = forward / forward_norm

        look_world = cam_world + forward * float(look_distance_m)
        return cam_world, look_world

    def _resolve_render_fov(self, fov_deg: Optional[float], fov_axis: Optional[str]) -> Tuple[float, str]:
        fov = float(self.settings["fov_deg"]) if fov_deg is None else float(fov_deg)
        axis = (self.settings.get("fov_axis", "horizontal") if fov_axis is None else str(fov_axis)).lower()

        if not (1.0 <= fov <= 179.0):
            raise ValueError("fov_deg must be in [1, 179] degrees.")
        if axis not in ("horizontal", "vertical"):
            raise ValueError("fov_axis must be 'horizontal' or 'vertical'.")
        return fov, axis

    def _set_camera_projection(
        self,
        camera: Any,
        width: int,
        height: int,
        fov_deg: float,
        fov_axis: str,
    ) -> None:
        """
        Configure projection with distinct horizontal and vertical FOV when possible.

        Open3D 0.13 supports intrinsic-based projection; this path allows separate
        horizontal/vertical FOV. If unavailable, we fall back to vertical FOV mode.
        """
        near_plane_m = 0.05
        far_plane_m = max(100.0, float(self.settings["ray_infinity_distance_m"]) * 2.0)
        aspect = float(width) / max(1.0, float(height))

        fov_type = (
            rendering.Camera.FovType.Horizontal
            if fov_axis == "horizontal"
            else rendering.Camera.FovType.Vertical
        )

        camera.set_projection(
            float(fov_deg),
            float(aspect),
            float(near_plane_m),
            float(far_plane_m),
            fov_type,
        )

    # ---------------- Render thread (Filament thread-affinity) --------

    def _render_worker(self) -> None:
        """
        Long-lived worker loop: pulls callables from the task queue, executes
        them on THIS thread (the only thread that ever touches Filament).
        On idle timeout, drops cached OffscreenRenderers to free resources.
        """
        # Renderer objects hold GPU/native state. Clearing cached renderers on idle
        # is a practical leak-prevention trick for long-running robot processes.
        # (This is not just "Python memory"; Filament/GL resources are involved.)
        idle_timeout_s = 5.0
        while True:
            try:
                task_fn, response_q = self._render_task_queue.get(timeout=idle_timeout_s)
            except queue.Empty:
                if self._renderers:
                    # OffscreenRenderer holds native resources; releasing references
                    # allows Python to drop them and Filament to reclaim memory.
                    self._renderers.clear()
                continue

            try:
                result = task_fn()
                response_q.put(("ok", result))
            except Exception as exc:
                response_q.put(("error", exc))

    def _run_on_render_thread(self, fn):
        """Submit a callable to the render thread, block for result."""
        # WARNING: do not "optimize" this away by calling fn() directly.
        # Any OffscreenRenderer/scene/material calls outside the render thread
        # can crash the process (Filament thread affinity).
        response_q: queue.Queue = queue.Queue()
        self._render_task_queue.put((fn, response_q))
        status, value = response_q.get()
        if status == "error":
            raise value
        return value

    # ---------------- Rendering ----------------

    def _get_renderer(self, width: int, height: int) -> rendering.OffscreenRenderer:
        # Cache by (width, height). Creating OffscreenRenderer repeatedly is expensive
        # and can churn GPU resources. We only create on the render thread.
        key = (width, height)
        if key in self._renderers:
            return self._renderers[key]
        r = rendering.OffscreenRenderer(width, height)
        self._renderers[key] = r
        return r

    def _clear_scene(self, scene: Any) -> None:
        try:
            scene.clear_geometry()
        except Exception:
            pass

    def _freeze_mesh(self, mesh: o3d.geometry.TriangleMesh) -> Optional[MeshSnapshot]:
        if mesh is None or mesh.is_empty() or not mesh.has_triangles():
            return None
        triangles = np.asarray(mesh.triangles)
        vertices = np.asarray(mesh.vertices)
        if triangles.size == 0 or vertices.size == 0:
            return None
        return MeshSnapshot(
            vertices=np.array(vertices, dtype=np.float32, copy=True),
            triangles=np.array(triangles, dtype=np.int32, copy=True),
        )

    def _freeze_objects(self, objs: List[SceneObject]) -> List[ObjectSnapshot]:
        frozen: List[ObjectSnapshot] = []
        for obj in objs:
            if not obj.raycast_visible:
                continue

            try:
                if obj.kind == "pointcloud":
                    pts = np.asarray(obj.geometry.points)
                    if pts.size == 0:
                        continue
                    frozen.append(ObjectSnapshot(
                        name=obj.name,
                        kind="pointcloud",
                        points=np.array(pts, dtype=np.float32, copy=True),
                    ))
                elif obj.kind == "mesh":
                    ms = self._freeze_mesh(obj.geometry)
                    if ms is None:
                        continue
                    frozen.append(ObjectSnapshot(
                        name=obj.name,
                        kind="mesh",
                        mesh=ms,
                    ))
            except Exception:
                continue
        return frozen

    def _render_scene(
        self,
        live_pcd_map: Optional[o3d.geometry.PointCloud],
        camera_world_pos: np.ndarray,
        look_at_world_pos: np.ndarray,
        width: int,
        height: int,
        include_robot: bool,
        effective_point_size: float,
        fov_deg: float,
        fov_axis: str,
        map_snapshot: Optional[MapSnapshot],
        cloud_alpha: float = 1.0,
    ) -> Tuple[np.ndarray, SceneSnapshot]:
        renderer = self._get_renderer(width, height)
        scene = renderer.scene
        self._clear_scene(scene)

        # Materials (Open3D 0.13):
        # - rendering.Material is the correct type for OffscreenRenderer scene.add_geometry
        # - MaterialRecord patterns you see online often target the GUI visualizer path,
        #   not OffscreenRenderer.
        unlit = rendering.Material()
        unlit.shader = "defaultUnlit"
        unlit.point_size = float(effective_point_size)

        # REAL transparency in Open3D 0.13: do NOT switch to newer shader strings like
        # "defaultUnlitTransparency" / "defaultLitTransparency".
        #
        # In 0.13 those names can map to a different (or missing) Filament material
        # package. Open3D then tries to set parameters (e.g. `srgbColor`) that the
        # underlying material doesn't have, and Filament aborts the entire process
        # with PreconditionPanic ("uniform named 'srgbColor' not found").
        #
        # Correct 0.13 approach: keep shader="defaultUnlit" and enable alpha via:
        #   - base_color RGBA (alpha in [0..1])
        #   - has_alpha = True
        if cloud_alpha < 1.0:
            unlit.base_color = [1.0, 1.0, 1.0, float(cloud_alpha)]
            unlit.has_alpha = True

        lit = rendering.Material()
        lit.shader = "defaultLit"

        # Floor (textured occupancy plane)
        floor_mesh, floor_mat = self._get_floor_visual_cached()
        scene.add_geometry("floor", floor_mesh, floor_mat if floor_mat is not None else lit)

        # Live Astra cloud:
        # We render from live Open3D geometry, but store a frozen float32 copy of points
        # into the snapshot for later raycasts. float32 is plenty for click/raycast
        # targeting and reduces memory/copy cost.
        astra_points_np = None
        if live_pcd_map is not None and live_pcd_map.has_points():
            scene.add_geometry("astra_cloud", live_pcd_map, unlit)

            # float32 is plenty for click targeting; halves memory and cache pressure.
            pts = np.asarray(live_pcd_map.points)
            if pts.size > 0:
                astra_points_np = np.array(pts, dtype=np.float32, copy=True)

        # Robot
        robot_mesh_render = None
        robot_mesh_frozen = None
        if include_robot:
            robot_mesh_render = self._create_robot_mesh_render_only()
            if robot_mesh_render is not None and not robot_mesh_render.is_empty():
                scene.add_geometry("robot", robot_mesh_render, lit)
                robot_mesh_frozen = self._freeze_mesh(robot_mesh_render)

        # ---- Phantasmata ----
        # Build and render all phantasma instances
        phantasma_objects: List[SceneObject] = []
        with self._instances_lock:
            instances_copy = dict(self._instances)

        for instance_name, instance_config in instances_copy.items():
            if not instance_config.get('render_visible', True):
                continue

            ctx = self._build_phantasma_context(instance_name, instance_config, map_snapshot)
            built_objects = self._build_phantasma_instance(
                instance_name, instance_config, ctx
            )

            if built_objects:
                for obj in built_objects:
                    if obj is None or not getattr(obj, 'render_visible', True):
                        continue

                    phantasma_objects.append(obj)

                    # Create material for this object
                    mat = rendering.Material()
                    shader = getattr(obj, 'shader', 'defaultLit')
                    mat.shader = shader

                    if getattr(obj, 'kind', 'mesh') == "pointcloud":
                        mat.point_size = float(getattr(obj, 'point_size', 3.0))

                    scene.add_geometry(
                        f"phantasma:{instance_name}:{getattr(obj, 'name', 'geom')}",
                        obj.geometry,
                        mat
                    )

        # Registered objects (legacy manual object management)
        objs_live: List[SceneObject] = []
        with self._objects_lock:
            for _, obj in self._objects.items():
                objs_live.append(obj)

        for obj in objs_live:
            if not obj.render_visible:
                continue
            mat = rendering.Material()
            mat.shader = obj.shader
            if obj.kind == "pointcloud":
                mat.point_size = float(obj.point_size)
            scene.add_geometry(f"obj:{obj.name}", obj.geometry, mat)

        # Freeze all objects (legacy + phantasmata) for raycasting
        all_raycast_objects = objs_live + phantasma_objects
        objs_frozen = self._freeze_objects(all_raycast_objects)

        # Camera projection (single FOV + axis)
        self._set_camera_projection(
            camera=scene.camera,
            width=width,
            height=height,
            fov_deg=float(fov_deg),
            fov_axis=str(fov_axis),
        )
        scene.camera.look_at(look_at_world_pos, camera_world_pos, [0.0, 0.0, 1.0])
        try:
            scene.scene.enable_sun_light(False)
        except Exception:
            pass
        scene.set_background([0.1, 0.1, 0.1, 1.0])
        # Background alpha stays 1.0. We are not compositing; transparency is only
        # for geometry blending. Setting bg alpha != 1 tends to produce confusing
        # results in offscreen captures unless you're explicitly doing RGBA pipelines.

        # Snapshot matrices
        view = _as_4x4(scene.camera.get_view_matrix())
        proj = _as_4x4(scene.camera.get_projection_matrix())

        render_id = uuid.uuid4().hex[:12]
        snapshot = SceneSnapshot(
            render_id=render_id,
            timestamp=time.time(),
            resolution=(height, width),
            camera_world_pos=np.array(camera_world_pos, dtype=np.float64, copy=True),
            look_at_world_pos=np.array(look_at_world_pos, dtype=np.float64, copy=True),
            view_matrix=view,
            projection_matrix=proj,
            ray_infinity_distance_m=float(self.settings["ray_infinity_distance_m"]),
            astra_points_map=astra_points_np,
            robot_mesh=robot_mesh_frozen,
            objects=objs_frozen,
            map_snapshot=map_snapshot,
        )

        # Render to image (Open3D gives RGB; convert to BGR for Logos consistency)
        img = np.asarray(renderer.render_to_image())
        if img.ndim == 3 and img.shape[2] == 4:
            img = img[:, :, :3]
        img_rgb = img.astype(np.uint8, copy=False)
        img_bgr = img_rgb[:, :, ::-1].copy()

        return img_bgr, snapshot

    # ---------------- Raycasting ----------------

    def _unproject_pixel_to_ray(
        self,
        px: float,
        py: float,
        snapshot: SceneSnapshot,
    ) -> Tuple[np.ndarray, np.ndarray]:
        height, width = snapshot.resolution
        inv_proj = np.linalg.inv(snapshot.projection_matrix)
        inv_view = np.linalg.inv(snapshot.view_matrix)

        x_ndc = (2.0 * px) / float(width) - 1.0
        y_ndc = 1.0 - (2.0 * py) / float(height)

        # clip-space point on the near plane
        ray_clip = np.array([x_ndc, y_ndc, -1.0, 1.0], dtype=np.float64)
        ray_eye = inv_proj @ ray_clip

        # w=0 turns it into a direction vector in eye space
        ray_eye = np.array([ray_eye[0], ray_eye[1], -1.0, 0.0], dtype=np.float64)

        ray_world_dir = (inv_view @ ray_eye)[:3]
        n = np.linalg.norm(ray_world_dir)
        if n < 1e-12:
            ray_world_dir = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        else:
            ray_world_dir /= n

        # Origin is camera position in world space according to the view matrix.
        ray_origin = (inv_view @ np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64))[:3]
        return ray_origin, ray_world_dir

    def _intersect_ray_with_pointcloud(
        self,
        ray_origin: np.ndarray,
        ray_dir: np.ndarray,
        points: np.ndarray,
        hit_radius_m: float,
    ) -> Optional[Tuple[float, np.ndarray]]:
        if points is None or points.size == 0:
            return None

        pts = points.astype(np.float64, copy=False)

        vec_op = pts - ray_origin
        t = vec_op @ ray_dir
        in_front = t > 0.0
        if not np.any(in_front):
            return None

        dist_sq = np.sum(vec_op * vec_op, axis=1) - (t * t)
        r2 = float(hit_radius_m) ** 2
        close = dist_sq < r2
        valid = in_front & close
        if not np.any(valid):
            return None

        idxs = np.where(valid)[0]
        best = idxs[np.argmin(t[valid])]
        return float(t[best]), pts[best].copy()

    def _intersect_ray_with_mesh_arrays_moller_trumbore(
        self,
        ray_origin: np.ndarray,
        ray_dir: np.ndarray,
        mesh: MeshSnapshot,
    ) -> Optional[Tuple[float, np.ndarray]]:
        if mesh is None or mesh.vertices is None or mesh.triangles is None:
            return None
        if mesh.vertices.size == 0 or mesh.triangles.size == 0:
            return None

        triangles = mesh.triangles
        vertices = mesh.vertices.astype(np.float64, copy=False)

        v0 = vertices[triangles[:, 0]]
        v1 = vertices[triangles[:, 1]]
        v2 = vertices[triangles[:, 2]]

        edge1 = v1 - v0
        edge2 = v2 - v0

        pvec = np.cross(ray_dir, edge2)
        det = np.sum(edge1 * pvec, axis=1)

        eps = 1e-8
        parallel = np.abs(det) < eps

        # Avoid inf/nan propagation: only invert where it's safe.
        inv_det = np.zeros_like(det, dtype=np.float64)
        inv_det[~parallel] = 1.0 / det[~parallel]

        tvec = ray_origin - v0
        u = np.sum(tvec * pvec, axis=1) * inv_det
        qvec = np.cross(tvec, edge1)
        v = np.sum(ray_dir * qvec, axis=1) * inv_det
        t = np.sum(edge2 * qvec, axis=1) * inv_det

        valid = (~parallel) & (t > eps) & (u >= 0.0) & (v >= 0.0) & ((u + v) <= 1.0)
        if not np.any(valid):
            return None

        min_t = float(np.min(t[valid]))
        hit_point = ray_origin + min_t * ray_dir
        return min_t, hit_point

    def _intersect_ray_with_floor(
        self,
        ray_origin: np.ndarray,
        ray_dir: np.ndarray,
        z_plane: float = 0.0,
    ) -> Optional[Tuple[float, np.ndarray]]:
        if abs(ray_dir[2]) < 1e-9:
            return None
        t = (z_plane - ray_origin[2]) / ray_dir[2]
        if t < 0.0:
            return None
        pt = ray_origin + t * ray_dir
        return float(t), pt

    # ---------------- HUD overlay ----------------

    @staticmethod
    def _overlay_hud(
        image: np.ndarray,
        elements: List[HudElement],
    ) -> np.ndarray:
        """
        Render HUD elements onto image (mutates in-place, also returns it).

        Note: This now delegates to vision.overlay_hud when available,
        keeping a fallback implementation for standalone testing.
        """
        if not elements:
            return image

        # Prefer the canonical implementation from vision.py
        if _HAS_VISION_HUD:
            return overlay_hud(image, elements)

        # Fallback implementation for standalone testing
        if not _HAS_CV2:
            return image

        h_img, w_img = image.shape[:2]

        groups: Dict[str, List[HudElement]] = {}
        for el in elements:
            anchor = el.anchor if el.anchor in HUD_ANCHORS else "top_left"
            groups.setdefault(anchor, []).append(el)

        for anchor in groups:
            groups[anchor].sort(key=lambda e: e.priority)

        for anchor, elems in groups.items():
            is_top = anchor.startswith("top")
            is_right = anchor.endswith("right")
            is_center = anchor.endswith("center")

            line_infos = []
            for el in elems:
                (tw, th), baseline = cv2.getTextSize(
                    el.text, el.font, el.font_scale, el.thickness
                )
                line_infos.append(((tw, th), baseline, el))

            margin = elems[0].margin_px if elems else 8
            if is_top:
                y_cursor = margin
            else:
                total_h = sum(ts[1] + bl + margin for (ts, bl, _) in line_infos)
                y_cursor = h_img - total_h - margin

            for (tw, th), baseline, el in line_infos:
                pad = el.margin_px
                line_h = th + baseline

                if is_center:
                    x = (w_img - tw) // 2
                elif is_right:
                    x = w_img - tw - pad
                else:
                    x = pad

                text_y = y_cursor + th

                if el.bg_color is not None:
                    x1 = max(x - pad, 0)
                    y1 = max(y_cursor - pad // 2, 0)
                    x2 = min(x + tw + pad, w_img)
                    y2 = min(text_y + baseline + pad // 2, h_img)

                    if el.bg_alpha >= 1.0:
                        cv2.rectangle(
                            image, (x1, y1), (x2, y2),
                            el.bg_color, cv2.FILLED,
                        )
                    elif el.bg_alpha > 0.0:
                        roi = image[y1:y2, x1:x2].copy()
                        overlay = np.full_like(roi, el.bg_color, dtype=np.uint8)
                        blended = cv2.addWeighted(
                            overlay, el.bg_alpha,
                            roi, 1.0 - el.bg_alpha,
                            0,
                        )
                        image[y1:y2, x1:x2] = blended

                cv2.putText(
                    image, el.text, (x, text_y),
                    el.font, el.font_scale, el.color, el.thickness,
                    cv2.LINE_AA,
                )

                y_cursor += line_h + pad

        return image

    def _build_system_hud(
        self,
        snapshot: SceneSnapshot,
        show_warnings: bool = True,
        show_frame_info: bool = True,
        show_stats: bool = False,
    ) -> List[HudElement]:
        """Build auto-generated system HUD elements."""
        elements: List[HudElement] = []

        if show_warnings:
            for i, warning in enumerate(self._get_render_warnings()):
                elements.append(HudElement(
                    text=f"! {warning}",
                    anchor="top_left",
                    color=(0, 200, 255),
                    bg_alpha=0.6,
                    font_scale=0.40,
                    priority=i,
                ))

        if show_frame_info:
            frame_str = self._active_world_frame or "raw (no TF)"
            elements.append(HudElement(
                text=f"frame: {frame_str}",
                anchor="bottom_left",
                color=(180, 180, 180),
                bg_alpha=0.3,
                font_scale=0.35,
                thickness=1,
                priority=0,
            ))

        if show_stats:
            n_pts = (
                snapshot.astra_points_map.shape[0]
                if snapshot.astra_points_map is not None
                else 0
            )
            n_objs = len(snapshot.objects)
            stats_lines = [
                f"pts: {n_pts:,}",
                f"objects: {n_objs}",
                f"res: {snapshot.resolution[1]}x{snapshot.resolution[0]}",
                f"id: {snapshot.render_id}",
            ]
            for i, line in enumerate(stats_lines):
                elements.append(HudElement(
                    text=line,
                    anchor="bottom_right",
                    color=(160, 160, 160),
                    bg_alpha=0.3,
                    font_scale=0.32,
                    thickness=1,
                    priority=i,
                ))

        return elements

    # ---------------- Public API ----------------

    @api_call(default_verbosity=Verbosity.ACK)
    def render(
        self,
        camera_pos_relative: Optional[Tuple[float, float, float]] = (-0.75, -1.0, 2.0),
        camera_pos_world: Optional[Tuple[float, float, float]] = None,
        look_at_relative: Optional[Tuple[float, float, float]] = (0.5, 0, 0.5),
        look_at_world: Optional[Tuple[float, float, float]] = None,
        rpy_deg: Optional[Tuple[float, float, float]] = None,
        rot_matrix_3x3: Optional[Union[np.ndarray, List[List[float]]]] = None,
        look_distance_m: float = 2.0,
        max_cloud_height_m: Optional[float] = None,
        resolution: Tuple[int, int] = (768, 768),  # (height, width)
        fov_deg: Optional[float] = None,
        fov_axis: Optional[str] = None,  # "horizontal" or "vertical"
        include_robot: bool = True,
        view: bool = True,
        save: bool = True,
        save_dir: str = "artifacts/chora",
        filename: Optional[str] = "debug.png",
        # Point cloud display — None = use self.settings value
        cloud_alpha: Optional[float] = None,
        cloud_density: Optional[float] = None,
        cloud_opacity: Optional[float] = None,
        cloud_point_size: Optional[float] = None,
        # Laser scan visualization — None = use self.settings value
        laser_scan_show: Optional[bool] = None,
        laser_scan_center_band_px: Optional[int] = None,
        laser_scan_color: Optional[List[float]] = None,
        # HUD options
        hud: Optional[List[HudElement]] = None,
        hud_warnings: bool = True,
        hud_frame_info: bool = True,
        hud_stats: bool = False,
    ) -> RenderResult:
        """
        Renders a view of my 3D 'map3d' from my virtual `chora` camera.

        This function constructs a 3D scene containing the known ROS map as a
        textured floor, the live point cloud from my Astra camera, and a model
        of my own body. It then renders a 2D image from a highly-configurable
        virtual camera. The output is a `RenderResult` object, which contains
        the BGR image and a rich `.meta` attribute holding the `SceneSnapshot`
        needed for subsequent `raycast` calls.

        Args:
            camera_pos_relative: (x, y, z) tuple for the camera's position
                relative to my `base_footprint` in meters. Defaults to a
                "shoulder camera" view [0.0, 0.0, 0.7].
            camera_pos_world: (x, y, z) tuple for the camera's absolute
                position in the map frame. Overrides `camera_pos_relative`.
            look_at_relative: (x, y, z) tuple for the point the camera
                should look at, relative to my `base_footprint`. Defaults
                to 1 meter in front of me [1.0, 0, 0.0].
            look_at_world: (x, y, z) tuple for the absolute map coordinate
                the camera should look at. Overrides all other targeting args.
            rpy_deg: (roll, pitch, yaw) tuple in degrees to specify camera
                orientation instead of a look_at point.
            resolution: (height, width) tuple for the output image.
            fov_horz_deg: Horizontal field-of-view in degrees. If omitted,
                uses `self.settings["fov_horz_deg"]`.
            fov_vert_deg: Vertical field-of-view in degrees. If omitted,
                uses `self.settings["fov_vert_deg"]`.
            include_robot: If True, includes a 3D model of myself in the scene.
            save: If True, saves the rendered image to disk.
            hud: An optional list of `HudElement` objects to overlay text on the
                final image for debugging or annotation.

        Returns:
            A `RenderResult` object, which is shaped like a `vision.CaptureResult`.
            It contains the `.image` (BGR numpy array) and a `.meta` dictionary
            with the crucial `SceneSnapshot` object required by `raycast()`.

        Note to self:
            This is my primary tool for situational awareness and off-line path
            planning. I can generate a top-down view to see my surroundings,
            or a third-person view to check my own position relative to obstacles.

            The most powerful workflow is:
            1. `render()` a view of a cluttered area.
            2. Analyze the resulting image, perhaps even using `logos.models.yolo`
            to find clear floor space.
            3. Choose a target pixel (y, x) in the image that represents a safe
            place to navigate to.
            4. Use `raycast()` on that pixel to get a real-world map coordinate.
            5. Use `logos.nav.go_to_abs()` with that coordinate.

            The `hud` argument is fantastic for adding an overlay of semantic or
            numerical context directly into my visual field.

            TODO: The 'phantasmata' concept mentioned in the old docstring is
            a game-changer. I should develop a system to add persistent 3D objects
            to this scene. I could model furniture I've seen, remember the last
            known location of an object, and render it in my mind palace. This
            would be the foundation of a true 3D semantic world model.
        """
        check_for_interrupt()

        width = int(resolution[1])
        height = int(resolution[0])
        if width <= 0 or height <= 0:
            raise ValueError("resolution must be positive (height, width).")
        
        effective_fov_deg, effective_fov_axis = self._resolve_render_fov(
            fov_deg=fov_deg,
            fov_axis=fov_axis,
        )

        self._clear_render_warnings()
        self._resolve_world_frame()

        # Freeze the map now so render + later raycast agree.
        map_snapshot = self._make_map_snapshot()

        self._start_camera_subscribers()
        try:
            # Clearing happens inside _start_camera_subscribers() so we don't
            # accidentally erase a freshly-arrived frame.
            ok = self._wait_for_frame(timeout_s=10.0)
            if not ok:
                raise RuntimeError("Timed out waiting for synchronized camera frame.")

            with self._frame_lock:
                pc_msg = self._latest_pc
                rgb_msg = self._latest_rgb
                info_msg = self._latest_info

            if pc_msg is None or rgb_msg is None or info_msg is None:
                raise RuntimeError("Camera streams not ready (missing synchronized triple).")
        finally:
            self._stop_camera_subscribers()

        # TF can lag on the very first call — retry with short sleeps.
        tf_max_retries = 5
        tf_retry_delay_s = 0.4
        camera_world = look_world = None
        for attempt in range(tf_max_retries):
            try:
                camera_world, look_world = self._resolve_camera_and_lookat(
                    camera_pos_relative=camera_pos_relative,
                    camera_pos_world=camera_pos_world,
                    look_at_relative=look_at_relative,
                    look_at_world=look_at_world,
                    rpy_deg=rpy_deg,
                    rot_matrix_3x3=(
                        np.asarray(rot_matrix_3x3)
                        if rot_matrix_3x3 is not None else None
                    ),
                    look_distance_m=look_distance_m,
                )
                break
            except RuntimeError as e:
                if "TF failed" in str(e) and attempt < tf_max_retries - 1:
                    print(
                        f"[map3d] TF not ready (attempt {attempt + 1}/"
                        f"{tf_max_retries}), retrying in "
                        f"{tf_retry_delay_s}s..."
                    )
                    time.sleep(tf_retry_delay_s)
                    continue
                raise

        live_pcd_map = self._build_live_colored_pcd_map(
            pc_msg=pc_msg,
            rgb_msg=rgb_msg,
            info_msg=info_msg,
            max_cloud_height_m=max_cloud_height_m,
            cloud_density=cloud_density,
            cloud_opacity=cloud_opacity,
            laser_scan_show=laser_scan_show,
            laser_scan_center_band_px=laser_scan_center_band_px,
            laser_scan_color=laser_scan_color,
        )

        effective_point_size = (
            cloud_point_size if cloud_point_size is not None
            else float(self.settings["render_point_size"])
        )

        effective_cloud_alpha = (
            cloud_alpha if cloud_alpha is not None
            else float(self.settings["cloud_alpha"])
        )
        effective_cloud_alpha = max(0.0, min(1.0, float(effective_cloud_alpha)))

        # All Open3D OffscreenRenderer work on the dedicated render thread.
        img_bgr, snapshot = self._run_on_render_thread(
            lambda: self._render_scene(
                live_pcd_map=live_pcd_map,
                camera_world_pos=camera_world,
                look_at_world_pos=look_world,
                width=width,
                height=height,
                include_robot=include_robot,
                effective_point_size=effective_point_size,
                fov_deg=float(effective_fov_deg),
                fov_axis=str(effective_fov_axis),
                map_snapshot=map_snapshot,
                cloud_alpha=effective_cloud_alpha,
            )
        )

        with self._renders_lock:
            self._renders[snapshot.render_id] = snapshot
            self._renders.move_to_end(snapshot.render_id)
            while len(self._renders) > self._renders_max:
                self._renders.popitem(last=False)

        # HUD overlay (caller thread; no Filament involved)
        all_hud: List[HudElement] = []
        all_hud.extend(self._build_system_hud(
            snapshot,
            show_warnings=hud_warnings,
            show_frame_info=hud_frame_info,
            show_stats=hud_stats,
        ))

        # Collect HUD contributions from phantasmata
        phantasma_hud = self._collect_hud_contributions(map_snapshot)
        all_hud.extend(phantasma_hud)

        if hud:
            all_hud.extend(hud)
        if all_hud:
            self._overlay_hud(img_bgr, all_hud)

        # Pose (best-effort)
        pose = None
        try:
            if logos_ros is not None and hasattr(logos_ros, "get_pose"):
                pose = logos_ros.get_pose()
        except Exception:
            pose = None

        result = RenderResult(
            image=img_bgr,
            source="map3d",
            timestamp=snapshot.timestamp,
            resolution=(height, width),
            photo_id=None,
            path=None,
            pose=pose,
            meta={
                "render_id": snapshot.render_id,
                "camera_world_pos": snapshot.camera_world_pos.tolist(),
                "look_at_world_pos": snapshot.look_at_world_pos.tolist(),
                "fov_deg": float(effective_fov_deg),
                "fov_axis": str(effective_fov_axis),
                "view_matrix": snapshot.view_matrix.tolist(),
                "projection_matrix": snapshot.projection_matrix.tolist(),
                "ray_infinity_distance_m": snapshot.ray_infinity_distance_m,
                "snapshot": snapshot,
            },
        )

        if save or view:
            out_path = None
            if filename:
                os.makedirs(save_dir, exist_ok=True)
                out_path = os.path.join(save_dir, filename)
            result.save(view=view, path=out_path)

        # Large temporaries (point arrays, renderer images) can benefit from
        # occasional reclamation in long-running robot processes.
        """     
       try:
            import gc
            gc.collect()
        except Exception:
            pass
        """

        return result

    @api_call(default_verbosity=Verbosity.ACK)
    def raycast(
        self,
        render: Union[RenderResult, str],
        yx: Tuple[float, float],
        include_floor: bool = True,
        include_astra: bool = True,
        include_robot: bool = True,
        include_objects: bool = True,
    ) -> RaycastHit:
        """
        Projects a 2D pixel from a `map3d` render back into the 3D world.
        """
        check_for_interrupt()

        snapshot = None
        if isinstance(render, RenderResult):
            if not render.meta or "snapshot" not in render.meta:
                raise ValueError("RenderResult has no snapshot in meta; cannot raycast.")
            snapshot = render.meta["snapshot"]
        else:
            render_id = str(render)
            with self._renders_lock:
                snapshot = self._renders.get(render_id)

        if snapshot is None:
            raise ValueError("Unknown render / render_id; cannot raycast.")

        y_norm, x_norm = float(yx[0]), float(yx[1])
        px = _norm1000_to_pixel(x_norm, snapshot.resolution[1])
        py = _norm1000_to_pixel(y_norm, snapshot.resolution[0])

        ray_origin, ray_dir = self._unproject_pixel_to_ray(px, py, snapshot)

        hits: List[Tuple[float, str, np.ndarray, Dict[str, Any]]] = []

        if include_astra and snapshot.astra_points_map is not None:
            hit = self._intersect_ray_with_pointcloud(
                ray_origin,
                ray_dir,
                snapshot.astra_points_map,
                hit_radius_m=float(self.settings["point_hit_radius"]),
            )
            if hit is not None:
                dist, pt = hit
                hits.append((dist, "astra_cloud", pt, {}))

        if include_objects and snapshot.objects:
            for obj in snapshot.objects:
                if obj.kind == "pointcloud" and obj.points is not None:
                    hit = self._intersect_ray_with_pointcloud(
                        ray_origin,
                        ray_dir,
                        obj.points,
                        hit_radius_m=float(self.settings["point_hit_radius"]),
                    )
                    if hit is not None:
                        dist, pt = hit
                        hits.append((dist, f"object:{obj.name}", pt, {}))
                elif obj.kind == "mesh" and obj.mesh is not None:
                    hit = self._intersect_ray_with_mesh_arrays_moller_trumbore(
                        ray_origin, ray_dir, obj.mesh
                    )
                    if hit is not None:
                        dist, pt = hit
                        hits.append((dist, f"object:{obj.name}", pt, {}))

        if include_robot and snapshot.robot_mesh is not None:
            hit = self._intersect_ray_with_mesh_arrays_moller_trumbore(
                ray_origin, ray_dir, snapshot.robot_mesh
            )
            if hit is not None:
                dist, pt = hit
                hits.append((dist, "robot", pt, {}))

        if include_floor:
            hit = self._intersect_ray_with_floor(ray_origin, ray_dir, z_plane=0.0)
            if hit is not None:
                dist, pt = hit
                floor_state = self._floor_state_at_map_snapshot(
                    float(pt[0]), float(pt[1]), snapshot.map_snapshot
                )
                hits.append((dist, "floor", pt, {"floor_state": floor_state}))

        if hits:
            hits.sort(key=lambda x: x[0])
            dist, hit_name, pt, meta = hits[0]
            floor_state = meta.get("floor_state")
            return RaycastHit(
                hit=hit_name,
                world_point=(float(pt[0]), float(pt[1]), float(pt[2])),
                distance_m=float(dist),
                floor_state=floor_state,
                meta={
                    "pixel_px": (float(py), float(px)),
                    "pixel_norm1000": (float(y_norm), float(x_norm)),
                },
            )

        dist = float(snapshot.ray_infinity_distance_m)
        pt = ray_origin + ray_dir * dist
        return RaycastHit(
            hit="infinity",
            world_point=(float(pt[0]), float(pt[1]), float(pt[2])),
            distance_m=dist,
            floor_state=None,
            meta={
                "pixel_px": (float(py), float(px)),
                "pixel_norm1000": (float(y_norm), float(x_norm)),
            },
        )


# --------------------------- Module Singleton ---------------------------

_CHORA_SINGLETON: Optional[Map3d] = None
_CHORA_LOCK = threading.Lock()


def get_map3d() -> Map3d:
    global _CHORA_SINGLETON
    with _CHORA_LOCK:
        if _CHORA_SINGLETON is None:
            _CHORA_SINGLETON = Map3d()
        return _CHORA_SINGLETON


@api_call(default_verbosity=Verbosity.ACK)
def render(*args, **kwargs) -> RenderResult:
    return get_map3d().render(*args, **kwargs)


@api_call(default_verbosity=Verbosity.ACK)
def raycast(*args, **kwargs) -> RaycastHit:
    return get_map3d().raycast(*args, **kwargs)


# ---- Module-level Phantasmata API ----

@api_call(default_verbosity=Verbosity.ACK)
def place(*args, **kwargs) -> None:
    """Place a phantasma instance. See Map3d.place() for details."""
    return get_map3d().place(*args, **kwargs)


@api_call(default_verbosity=Verbosity.ACK)
def remove(*args, **kwargs) -> None:
    """Remove a phantasma instance. See Map3d.remove() for details."""
    return get_map3d().remove(*args, **kwargs)


@api_call(default_verbosity=Verbosity.ACK)
def update_instance(*args, **kwargs) -> None:
    """Update phantasma instance params. See Map3d.update_instance() for details."""
    return get_map3d().update_instance(*args, **kwargs)


@api_call(default_verbosity=Verbosity.ACK)
def move_instance(*args, **kwargs) -> None:
    """Move a phantasma instance. See Map3d.move_instance() for details."""
    return get_map3d().move_instance(*args, **kwargs)


@api_call(default_verbosity=Verbosity.ACK)
def set_visible(*args, **kwargs) -> None:
    """Set phantasma visibility. See Map3d.set_visible() for details."""
    return get_map3d().set_visible(*args, **kwargs)


def list_instances() -> Dict[str, Dict[str, Any]]:
    """List all phantasma instances. See Map3d.list_instances() for details."""
    return get_map3d().list_instances()


def describe_instance(name: str) -> Dict[str, Any]:
    """Describe a phantasma instance. See Map3d.describe_instance() for details."""
    return get_map3d().describe_instance(name)


def list_phantasmata() -> List[str]:
    """List available phantasma modules. See Map3d.list_phantasmata() for details."""
    return get_map3d().list_phantasmata()


def describe_phantasma(object_name: str) -> Dict[str, Any]:
    """Describe a phantasma module. See Map3d.describe_phantasma() for details."""
    return get_map3d().describe_phantasma(object_name)


@api_call(default_verbosity=Verbosity.ACK)
def reload_mind_palace() -> None:
    """Reload mind_palace.yaml. See Map3d.reload_mind_palace() for details."""
    return get_map3d().reload_mind_palace()


@api_call(default_verbosity=Verbosity.ACK)
def rebuild(name: Optional[str] = None) -> None:
    """Force rebuild phantasmata. See Map3d.rebuild() for details."""
    return get_map3d().rebuild(name)


__all__ = [
    # Data structures
    "RenderResult",
    "RaycastHit",
    "SceneObject",
    "SceneSnapshot",
    "HudElement",
    "HUD_ANCHORS",
    "HUD_FONT_SIMPLEX",
    "HUD_FONT_PLAIN",
    "HUD_FONT_DUPLEX",
    "HUD_FONT_SMALL",
    # Core class and singleton
    "Map3d",
    "get_map3d",
    # Render/raycast API
    "render",
    "raycast",
    # Phantasmata API
    "place",
    "remove",
    "update_instance",
    "move_instance",
    "set_visible",
    "list_instances",
    "describe_instance",
    "list_phantasmata",
    "describe_phantasma",
    "reload_mind_palace",
    "rebuild",
]
