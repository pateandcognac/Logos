# src/logos/chora.py
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

This allows me to visually plan paths, understand spatial relationships, and
select navigation goals in a way that transcends my physical sensors.

# VERY, VERY IMPORTANT: This code uses Open3d 0.13
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
import os
import time
import math
import threading
import queue
import importlib
import uuid
import numpy as np

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

from logos.logos_mesh import build_logos_mesh
mesh = build_logos_mesh()


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
    astra_points_map: Optional[np.ndarray] = None  # (N, 3) float64 in map frame
    robot_mesh: Optional[Any] = None  # o3d.geometry.TriangleMesh
    objects: List[SceneObject] = field(default_factory=list)

    # Occupancy for floor semantics:
    occupancy_grid: Optional[OccupancyGrid] = None


@dataclass
class RenderResult:
    """
    CaptureResult-shaped return for mind-palace rendering.
    image is BGR uint8 for consistency with the rest of Logos vision tooling.
    """
    image: np.ndarray
    source: str = "chora"
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
            self.photo_id = self.meta.get("render_id", uuid.uuid4().hex[:12])
            save_dir = "artifacts/chora"
            os.makedirs(save_dir, exist_ok=True)
            self.path = path or os.path.join(save_dir, f"chora_{self.photo_id}.png")
            cv2.imwrite(self.path, self.image)
        
        if view:
            self.view()
        return self.path

    def view(self) -> None:
        if self.path is None:
            self.save()
        print(f'<file path="{self.path}">theoria</file>')


# Named anchor positions for HUD elements.  Elements sharing an anchor
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
HUD_FONT_MONO = 7           # cv2.FONT_HERSHEY_SCRIPT_SIMPLEX — actually not mono
# For actual monospace, FONT_HERSHEY_PLAIN (1) is closest in OpenCV.






@dataclass
class HudElement:
    """
    A single text element to overlay on a rendered image.

    Positioning uses named anchors (see HUD_ANCHORS).  Multiple elements
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
    # Normalize to be safe
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


def _euler_rpy_deg_to_rot_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Roll/pitch/yaw in degrees -> 3x3 rotation matrix, ROS convention (XYZ intrinsic)."""
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


# --------------------------- Core Chora System ---------------------------

class Chora:
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
            # In Logos this is typically already done, but this makes chora standalone-safe.
            rospy.init_node("logos_chora", anonymous=True, disable_signals=True)

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

        # Occupancy grid + cached floor mesh
        self._map_lock = threading.Lock()
        self._occupancy_grid: Optional[OccupancyGrid] = None
        self._occupancy_np: Optional[np.ndarray] = None  # (H, W) int8/int16
        self._floor_mesh: Optional[o3d.geometry.TriangleMesh] = None
        self._floor_mesh_stamp: Optional[rospy.Time] = None

        # Floor visual cache (textured plane)
        self._floor_visual_mesh: Optional[o3d.geometry.TriangleMesh] = None
        self._floor_visual_mat: Any = None
        self._floor_visual_stamp: Optional[rospy.Time] = None
        self._floor_visual_dims: Optional[Tuple[int, int]] = None  # (w, h)

        # Render caching
        self._renderers: Dict[Tuple[int, int], rendering.OffscreenRenderer] = {}
        self._renders: Dict[str, SceneSnapshot] = {}
        self._renders_lock = threading.Lock()

        # Objects (future: phantasmata)
        self._objects_lock = threading.Lock()
        self._objects: Dict[str, SceneObject] = {}

        # Per-render warning accumulator (cleared at start of each render).
        # Warnings are auto-displayed on the HUD unless suppressed.
        self._render_warnings: List[str] = []
        self._render_warnings_lock = threading.Lock()

        # Active world frame: tracks what TF frame we're actually using
        # for the current render ("map", "odom", or None for identity).
        self._active_world_frame: Optional[str] = None

        # Settings
        self.settings = {
            "voxel_downsample": False,
            "voxel_size": 0.035,
            "stat_outlier_removal": True,
            "sor_neighbors": 50,
            "sor_std_ratio": 2.0,
            "point_hit_radius": 0.05,  # meters
            "ray_infinity_distance_m": 50.0,
            "render_point_size": 3.0,
        }

        # Dedicated render thread: Open3D 0.13's Filament backend requires
        # that ALL OffscreenRenderer usage happens on the same OS thread that
        # created it. ROS callbacks / Logos execution may dispatch render()
        # from varying threads, so we funnel all Open3D rendering work through
        # a single persistent worker thread via a task queue.
        self._render_task_queue: queue.Queue = queue.Queue()
        self._render_thread = threading.Thread(
            target=self._render_worker, daemon=True, name="chora-render"
        )
        self._render_thread.start()

        self._start_subscribers()

    # ---------------- ROS plumbing ----------------

    def _get_tf_buffer(self):
        if logos_ros is not None and hasattr(logos_ros, "get_tf_buffer"):
            return logos_ros.get_tf_buffer()

        # Fallback: local singleton
        if self._tf_buffer is None:
            self._tf_buffer = tf2_ros.Buffer()
            self._tf_listener = tf2_ros.TransformListener(self._tf_buffer)
        return self._tf_buffer

    def _start_subscribers(self) -> None:
        # Map
        self._map_sub = rospy.Subscriber(
            self.map_topic,
            OccupancyGrid,
            self._map_callback,
            queue_size=1,
        )

        # Synchronized camera streams
        pc_sub = message_filters.Subscriber(self.points_topic, PointCloud2)
        rgb_sub = message_filters.Subscriber(self.rgb_image_topic, Image)
        info_sub = message_filters.Subscriber(self.rgb_info_topic, CameraInfo)

        ts = message_filters.ApproximateTimeSynchronizer(
            [pc_sub, rgb_sub, info_sub],
            queue_size=10,
            slop=0.2,
        )
        ts.registerCallback(self._camera_sync_callback)

        # Hold references so GC doesn't kill them
        self._pc_sub = pc_sub
        self._rgb_sub = rgb_sub
        self._info_sub = info_sub
        self._sync = ts

    def _camera_sync_callback(self, pc_msg: PointCloud2, rgb_msg: Image, info_msg: CameraInfo) -> None:
        with self._frame_lock:
            self._latest_pc = pc_msg
            self._latest_rgb = rgb_msg
            self._latest_info = info_msg
            # Use ROS stamp if present; else wall time
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

            # Old detailed mesh cache (if you still keep it around)
            self._floor_mesh = None
            self._floor_mesh_stamp = msg.header.stamp if hasattr(msg, "header") else None

            # New textured-plane cache
            self._floor_visual_mesh = None
            self._floor_visual_mat = None
            self._floor_visual_stamp = msg.header.stamp if hasattr(msg, "header") else None
            self._floor_visual_dims = None

    def _wait_for_frame(self, timeout_s: float = 2.0) -> bool:
        self._frame_event.clear()
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
        Minimal future-proof loader:
        expects phantasmata/<name>.py to define build() -> SceneObject or List[SceneObject].
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

    # ---------------- Mesh/PCD preprocessing ----------------

    def _preprocess_point_cloud(self, pcd: o3d.geometry.PointCloud) -> o3d.geometry.PointCloud:
        processed = o3d.geometry.PointCloud()
        processed.points = o3d.utility.Vector3dVector(np.asarray(pcd.points).copy())

        if pcd.has_colors():
            processed.colors = o3d.utility.Vector3dVector(np.asarray(pcd.colors).copy())
        else:
            processed.paint_uniform_color([0.8, 0.2, 0.2])

        if self.settings["voxel_downsample"] and processed.has_points():
            processed = processed.voxel_down_sample(self.settings["voxel_size"])

        if self.settings["stat_outlier_removal"] and processed.has_points():
            nn = int(self.settings["sor_neighbors"])
            if len(processed.points) > nn:
                processed, _ = processed.remove_statistical_outlier(
                    nb_neighbors=nn,
                    std_ratio=float(self.settings["sor_std_ratio"]),
                )
        return processed

    def _transform_pcd_to_map(self, pcd: o3d.geometry.PointCloud, source_frame: str) -> Optional[o3d.geometry.PointCloud]:
        world_frame = self._get_world_frame()

        # Identity fallback: no transform, return a copy as-is
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
    ) -> Optional[o3d.geometry.PointCloud]:
        """
        Build a colored point cloud, transformed into map frame.
        Uses registered points topic so (x,y,z) should align with RGB intrinsics.
        """
        cv_bgr = self.bridge.imgmsg_to_cv2(rgb_msg, desired_encoding="bgr8")
        h_img, w_img = cv_bgr.shape[:2]

        fx, fy = float(info_msg.K[0]), float(info_msg.K[4])
        cx, cy = float(info_msg.K[2]), float(info_msg.K[5])

        points: List[List[float]] = []
        colors: List[List[float]] = []

        # Looping is OK given your stated frequency (and gives robustness without extra deps).
        # We still interrupt-check periodically.
        step_check = 5000
        i = 0

        for (x, y, z) in pc2.read_points(pc_msg, field_names=("x", "y", "z"), skip_nans=True):
            i += 1
            if i % step_check == 0:
                check_for_interrupt()

            if z <= 0.0:
                continue

            u = int(fx * x / z + cx)
            v = int(fy * y / z + cy)
            if 0 <= u < w_img and 0 <= v < h_img:
                b, g, r = cv_bgr[v, u]
                points.append([float(x), float(y), float(z)])
                colors.append([r / 255.0, g / 255.0, b / 255.0])  # store as RGB for Open3D

        if not points:
            return None

        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(np.asarray(points, dtype=np.float64))
        pcd.colors = o3d.utility.Vector3dVector(np.asarray(colors, dtype=np.float64))

        pcd_map = self._transform_pcd_to_map(pcd, pc_msg.header.frame_id)
        if pcd_map is None or not pcd_map.has_points():
            return None

        # Optional ceiling clip in MAP frame
        if max_cloud_height_m is not None:
            pts = np.asarray(pcd_map.points)
            keep = np.where(pts[:, 2] < float(max_cloud_height_m))[0]
            pcd_map = pcd_map.select_by_index(keep)

        return self._preprocess_point_cloud(pcd_map)

    # ---------------- Floor mesh + occupancy semantics ----------------

    def _floor_state_at(self, x: float, y: float) -> str:
        with self._map_lock:
            grid = self._occupancy_grid
            occ = self._occupancy_np

        if grid is None or occ is None:
            return "unmapped"

        res = float(grid.info.resolution)
        origin_x = float(grid.info.origin.position.x)
        origin_y = float(grid.info.origin.position.y)
        w = int(grid.info.width)
        h = int(grid.info.height)

        j = int((x - origin_x) / res)
        i = int((y - origin_y) / res)

        if i < 0 or i >= h or j < 0 or j >= w:
            return "unmapped"

        val = int(occ[i, j])
        if 0 <= val <= 25:
            return "map_open"
        if val >= 75:
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

        # Color policy (RGB)
        # open: near-white, occupied: near-black, unknown: mid gray
        open_rgb = np.array([230, 230, 230], dtype=np.uint8)
        occ_rgb = np.array([30, 30, 30], dtype=np.uint8)
        unk_rgb = np.array([128, 128, 128], dtype=np.uint8)

        # Masking
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
        World X/Y maps linearly to U/V across the plane.
        """
        w_m = float(width_cells) * float(res)
        h_m = float(height_cells) * float(res)

        # Four corners in world coordinates
        x0 = float(origin_x)
        y0 = float(origin_y)
        x1 = x0 + w_m
        y1 = y0 + h_m

        # Vertices: (x0,y0), (x1,y0), (x1,y1), (x0,y1)
        vertices = np.array(
            [
                [x0, y0, z],
                [x1, y0, z],
                [x1, y1, z],
                [x0, y1, z],
            ],
            dtype=np.float64,
        )

        triangles = np.array(
            [
                [0, 1, 2],
                [0, 2, 3],
            ],
            dtype=np.int32,
        )

        # UV convention:
        # (x0,y0)->(0,0), (x1,y0)->(1,0), (x1,y1)->(1,1), (x0,y1)->(0,1)
        # Open3D expects triangle_uvs as (num_triangles*3, 2)
        uvs = np.array(
            [
                [0.0, 0.0],  # v0
                [1.0, 0.0],  # v1
                [1.0, 1.0],  # v2
                [0.0, 0.0],  # v0
                [1.0, 1.0],  # v2
                [0.0, 1.0],  # v3
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
        Open3D 0.13: OffscreenRenderer textures usually go in MaterialRecord.albedo_img.
        We provide RGBA to avoid edge-case channel handling.
        """
        # Ensure uint8 contiguous
        tex_rgb = np.ascontiguousarray(tex_rgb.astype(np.uint8, copy=False))

        # Add opaque alpha channel (RGBA)
        h, w = tex_rgb.shape[:2]
        alpha = np.full((h, w, 1), 255, dtype=np.uint8)
        tex_rgba = np.concatenate([tex_rgb, alpha], axis=2)

        tex_img = o3d.geometry.Image(tex_rgba)

        # Prefer MaterialRecord for rendering.OffscreenRenderer
        if _HAS_MAT_RECORD and MaterialRecord is not None:
            mat = MaterialRecord()
            mat.shader = "defaultUnlit"  # try "defaultLit" if you still see white

            # The important bit for 0.13:
            if hasattr(mat, "albedo_img"):
                mat.albedo_img = tex_img
            else:
                # Some builds might expose it differently; keep a fallback:
                if hasattr(mat, "base_color_texture"):
                    mat.base_color_texture = tex_img  # type: ignore

            # Keep base_color neutral so it doesn't tint the texture
            if hasattr(mat, "base_color"):
                mat.base_color = [1.0, 1.0, 1.0, 1.0]

            return mat

        # Fallback: try rendering.Material (less reliable in 0.13 offscreen)
        try:
            mat = rendering.Material()
            mat.shader = "defaultUnlit"
            if hasattr(mat, "albedo_img"):
                mat.albedo_img = tex_img
            if hasattr(mat, "base_color"):
                mat.base_color = [1.0, 1.0, 1.0, 1.0]
            return mat
        except Exception:
            return None
        
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

        # Build texture (RGB)
        tex_rgb = self._build_occupancy_texture_rgb(
            occ=occ,
            flip_y=True,  # this is the one you might toggle if orientation is mirrored
        )

        # Build plane mesh + UVs
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
            # Texture failed for some reason; still return a neutral plane
            mesh.paint_uniform_color([0.35, 0.35, 0.35])
            mesh.compute_vertex_normals()

        with self._map_lock:
            self._floor_visual_mesh = mesh
            self._floor_visual_mat = mat
            self._floor_visual_stamp = stamp
            self._floor_visual_dims = (width_cells, height_cells)

        return mesh, mat


    # ---------------- Robot model (optional) ----------------

    def _get_robot_transform_map(self) -> Optional[np.ndarray]:
        world_frame = self._get_world_frame()

        # Identity fallback
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

    def _create_robot_mesh(self) -> Optional[o3d.geometry.TriangleMesh]:
        tfm = self._get_robot_transform_map()
        if tfm is None:
            return None

        # Build the full Logos robot model (cached after first call)
        if not hasattr(self, '_logos_base_mesh') or self._logos_base_mesh is None:
            from logos.logos_mesh import build_logos_mesh
            self._logos_base_mesh = build_logos_mesh()

        # Deep copy so the transform doesn't accumulate
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
            # Deduplicate identical warnings within a single render pass
            if msg not in self._render_warnings:
                self._render_warnings.append(msg)
                print(f"[chora] WARN: {msg}")

    def _get_render_warnings(self) -> List[str]:
        with self._render_warnings_lock:
            return list(self._render_warnings)

    # ---------------- World-frame fallback ----------------

    def _resolve_world_frame(self) -> str:
        """
        Determine the best available world frame for this render pass.
        Tries map_frame first, then 'odom', then gives up (identity).
        Caches the result in self._active_world_frame for the duration
        of the render pass so all TF lookups are consistent.
        """
        buf = self._get_tf_buffer()

        # Try preferred frame
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

        # Nothing works — identity fallback
        self._add_render_warning(
            "No TF frames available (map/odom) — rendering in base frame"
        )
        self._active_world_frame = ""
        return ""

    def _get_world_frame(self) -> str:
        """Return the active world frame for this render pass."""
        if self._active_world_frame is not None:
            return self._active_world_frame
        return self.map_frame  # default if called outside a render pass

    # ---------------- Camera targeting ----------------

    def _point_base_to_map(self, xyz_base: Tuple[float, float, float]) -> Optional[np.ndarray]:
        buf = self._get_tf_buffer()
        world_frame = self._get_world_frame()

        # If no TF frame is available, return raw coordinates (identity).
        if not world_frame:
            return np.array(xyz_base, dtype=np.float64)

        pt = PointStamped()
        pt.header.stamp = rospy.Time(0)
        pt.point.x, pt.point.y, pt.point.z = xyz_base

        # Try a couple likely base frames as a fallback (cheap and very worth it)
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

        print(f"[chora] TF point transform failed ({candidate_frames} -> {world_frame}): {last_err}")
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
        """
        Reduce all supported targeting modes to:
          camera_world_pos, look_at_world_pos
        """
        if camera_pos_world is not None:
            cam_world = np.array(camera_pos_world, dtype=np.float64)
        elif camera_pos_relative is not None:
            cam_world = self._point_base_to_map(camera_pos_relative)
            if cam_world is None:
                raise RuntimeError("TF failed: could not transform camera_pos_relative to map.")
        else:
            raise ValueError("Must supply camera_pos_relative or camera_pos_world.")

        if look_at_world is not None:
            look_world = np.array(look_at_world, dtype=np.float64)
            return cam_world, look_world

        if look_at_relative is not None:
            look_world = self._point_base_to_map(look_at_relative)
            if look_world is None:
                raise RuntimeError("TF failed: could not transform look_at_relative to map.")
            return cam_world, look_world

        # Orientation mode: compute forward vector and synthesize a look-at point.
        if rot_matrix_3x3 is not None:
            rot = np.array(rot_matrix_3x3, dtype=np.float64).reshape((3, 3))
        elif rpy_deg is not None:
            rot = _euler_rpy_deg_to_rot_matrix(*rpy_deg)
        else:
            raise ValueError("Must supply one of look_at_relative, look_at_world, rpy_deg, or rot_matrix_3x3.")

        # Assume camera forward is +X in its local frame *in map convention*.
        # If you later want optical-style forward, we can flip this cleanly here.
        forward = rot @ np.array([1.0, 0.0, 0.0], dtype=np.float64)
        forward_norm = np.linalg.norm(forward)
        if forward_norm < 1e-9:
            forward = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        else:
            forward = forward / forward_norm

        look_world = cam_world + forward * float(look_distance_m)
        return cam_world, look_world

    # ---------------- Render thread (Filament thread-affinity fix) --------

    def _render_worker(self) -> None:
        """
        Long-lived worker loop: pulls callables from the task queue, executes
        them on THIS thread (the only thread that ever touches Filament), and
        sends results back via a per-task response queue.

        On idle timeout, destroys cached OffscreenRenderers so Filament's
        job-system threads can shut down and stop burning CPU.
        """
        _IDLE_TIMEOUT_S = 5.0
        while True:
            try:
                task_fn, response_q = self._render_task_queue.get(
                    timeout=_IDLE_TIMEOUT_S
                )
            except queue.Empty:
                # Idle: tear down Filament to free CPU.  Renderers will be
                # transparently recreated on the next render() call.
                if self._renderers:
                    self._renderers.clear()
                continue

            try:
                result = task_fn()
                response_q.put(("ok", result))
            except Exception as exc:
                response_q.put(("error", exc))

    def _run_on_render_thread(self, fn):
        """
        Submit a zero-arg callable to the dedicated render thread, block until
        it completes, and return its result (or re-raise its exception).
        """
        response_q: queue.Queue = queue.Queue()
        self._render_task_queue.put((fn, response_q))
        status, value = response_q.get()
        if status == "error":
            raise value
        return value

    # ---------------- Rendering ----------------

    def _get_renderer(self, width: int, height: int) -> rendering.OffscreenRenderer:
        key = (width, height)
        if key in self._renderers:
            return self._renderers[key]
        r = rendering.OffscreenRenderer(width, height)
        self._renderers[key] = r
        return r

    def _clear_scene(self, scene: Any) -> None:
        # Open3D 0.13 has clear_geometry(); if not, caller should rebuild renderer.
        try:
            scene.clear_geometry()
        except Exception:
            pass

    def _render_scene(
        self,
        live_pcd_map: Optional[o3d.geometry.PointCloud],
        camera_world_pos: np.ndarray,
        look_at_world_pos: np.ndarray,
        width: int,
        height: int,
        include_robot: bool,
    ) -> Tuple[np.ndarray, SceneSnapshot]:
        renderer = self._get_renderer(width, height)
        scene = renderer.scene
        self._clear_scene(scene)

        # Materials
        unlit = rendering.Material()
        unlit.shader = "defaultUnlit"
        unlit.point_size = float(self.settings["render_point_size"])

        lit = rendering.Material()
        lit.shader = "defaultLit"
        
        # Floor (textured occupancy plane)
        floor_mesh, floor_mat = self._get_floor_visual_cached()
        if floor_mat is None:
            scene.add_geometry("floor", floor_mesh, lit)
        else:
            scene.add_geometry("floor", floor_mesh, floor_mat)

        # Live Astra cloud
        astra_points_np = None
        if live_pcd_map is not None and live_pcd_map.has_points():
            scene.add_geometry("astra_cloud", live_pcd_map, unlit)
            astra_points_np = np.asarray(live_pcd_map.points).copy()

        # Robot (rendered, raycast optional at query time)
        robot_mesh = None
        if include_robot:
            robot_mesh = self._create_robot_mesh()
            if robot_mesh is not None and not robot_mesh.is_empty():
                scene.add_geometry("robot", robot_mesh, lit)

        # Registered objects (phantasmata)
        objs: List[SceneObject] = []
        with self._objects_lock:
            for name, obj in self._objects.items():
                objs.append(obj)

        for obj in objs:
            if not obj.render_visible:
                continue
            mat = rendering.Material()
            mat.shader = obj.shader
            if obj.kind == "pointcloud":
                mat.point_size = float(obj.point_size)
            scene.add_geometry(f"obj:{obj.name}", obj.geometry, mat)

        # Camera
        scene.camera.look_at(look_at_world_pos, camera_world_pos, [0.0, 0.0, 1.0])
        try:
            scene.scene.enable_sun_light(False)
        except Exception:
            pass
        scene.set_background([0.1, 0.1, 0.1, 1.0])

        # Snapshot
        view = np.array(scene.camera.get_view_matrix(), dtype=np.float64)
        proj = np.array(scene.camera.get_projection_matrix(), dtype=np.float64)

        render_id = uuid.uuid4().hex[:12]
        snapshot = SceneSnapshot(
            render_id=render_id,
            timestamp=time.time(),
            resolution=(height, width),
            camera_world_pos=camera_world_pos.copy(),
            look_at_world_pos=look_at_world_pos.copy(),
            view_matrix=view,
            projection_matrix=proj,
            ray_infinity_distance_m=float(self.settings["ray_infinity_distance_m"]),
            astra_points_map=astra_points_np,
            robot_mesh=robot_mesh,
            objects=objs,
            occupancy_grid=self._occupancy_grid,
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

        ray_clip = np.array([x_ndc, y_ndc, -1.0, 1.0], dtype=np.float64)
        ray_eye = inv_proj @ ray_clip
        ray_eye = np.array([ray_eye[0], ray_eye[1], -1.0, 0.0], dtype=np.float64)

        ray_world_dir = (inv_view @ ray_eye)[:3]
        n = np.linalg.norm(ray_world_dir)
        if n < 1e-12:
            ray_world_dir = np.array([1.0, 0.0, 0.0], dtype=np.float64)
        else:
            ray_world_dir /= n

        ray_origin = (inv_view @ np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float64))[:3]
        return ray_origin, ray_world_dir

    def _intersect_ray_with_pointcloud(
        self,
        ray_origin: np.ndarray,
        ray_dir: np.ndarray,
        points: np.ndarray,
        hit_radius_m: float,
    ) -> Optional[Tuple[float, np.ndarray]]:
        """
        Closest point-to-ray within radius.
        points: (N,3) in world.
        """
        if points.size == 0:
            return None

        vec_op = points - ray_origin
        t = vec_op @ ray_dir  # (N,)
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
        return float(t[best]), points[best].copy()

    def _intersect_ray_with_mesh_moller_trumbore(
        self,
        ray_origin: np.ndarray,
        ray_dir: np.ndarray,
        mesh: o3d.geometry.TriangleMesh,
    ) -> Optional[Tuple[float, np.ndarray]]:
        if mesh is None or mesh.is_empty() or not mesh.has_triangles():
            return None

        triangles = np.asarray(mesh.triangles)
        vertices = np.asarray(mesh.vertices)

        v0 = vertices[triangles[:, 0]]
        v1 = vertices[triangles[:, 1]]
        v2 = vertices[triangles[:, 2]]

        edge1 = v1 - v0
        edge2 = v2 - v0

        pvec = np.cross(ray_dir, edge2)
        det = np.sum(edge1 * pvec, axis=1)

        eps = 1e-8
        parallel = np.abs(det) < eps
        inv_det = 1.0 / det

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

    def _intersect_ray_with_floor(self, ray_origin: np.ndarray, ray_dir: np.ndarray, z_plane: float = 0.0) -> Optional[Tuple[float, np.ndarray]]:
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
        Elements are grouped by anchor, sorted by priority, and stacked.

        Uses cv2 for text rendering — no Filament involvement, so this
        can safely run on any thread.
        """
        if not _HAS_CV2 or not elements:
            return image

        h_img, w_img = image.shape[:2]

        # Group elements by anchor
        groups: Dict[str, List[HudElement]] = {}
        for el in elements:
            anchor = el.anchor if el.anchor in HUD_ANCHORS else "top_left"
            groups.setdefault(anchor, []).append(el)

        # Sort each group by priority
        for anchor in groups:
            groups[anchor].sort(key=lambda e: e.priority)

        for anchor, elems in groups.items():
            # Determine starting position and stacking direction
            is_top = anchor.startswith("top")
            is_right = anchor.endswith("right")
            is_center = anchor.endswith("center")

            # Measure all lines first to compute layout
            line_infos = []  # [(text_size, baseline, elem), ...]
            for el in elems:
                (tw, th), baseline = cv2.getTextSize(
                    el.text, el.font, el.font_scale, el.thickness
                )
                line_infos.append(((tw, th), baseline, el))

            # Stack lines from anchor edge
            margin = elems[0].margin_px if elems else 8
            if is_top:
                y_cursor = margin
            else:
                # Bottom: start from bottom, stack upward.
                # Pre-compute total height.
                total_h = sum(
                    ts[1] + bl + margin for (ts, bl, _) in line_infos
                )
                y_cursor = h_img - total_h - margin

            for (tw, th), baseline, el in line_infos:
                pad = el.margin_px
                line_h = th + baseline

                # X position
                if is_center:
                    x = (w_img - tw) // 2
                elif is_right:
                    x = w_img - tw - pad
                else:
                    x = pad

                # Y position (cv2 putText y is baseline)
                text_y = y_cursor + th

                # Background rectangle (with alpha blending)
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
                        # Alpha blend: extract ROI, blend, paste back
                        roi = image[y1:y2, x1:x2].copy()
                        overlay = np.full_like(roi, el.bg_color, dtype=np.uint8)
                        blended = cv2.addWeighted(
                            overlay, el.bg_alpha,
                            roi, 1.0 - el.bg_alpha,
                            0,
                        )
                        image[y1:y2, x1:x2] = blended

                # Text
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
        """
        Build auto-generated system HUD elements (warnings, frame info, etc).
        These are displayed in addition to any user-supplied HUD elements.
        """
        elements: List[HudElement] = []

        # Warnings — yellow, top-left, highest priority
        if show_warnings:
            for i, warning in enumerate(self._get_render_warnings()):
                elements.append(HudElement(
                    text=f"! {warning}",
                    anchor="top_left",
                    color=(0, 200, 255),  # BGR yellow-orange
                    bg_alpha=0.6,
                    font_scale=0.40,
                    priority=i,
                ))

        # Frame info — subtle, bottom-left
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

        # Optional stats
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
        camera_pos_relative: Optional[Tuple[float, float, float]] = (0.0, 0.0, 0.7),
        camera_pos_world: Optional[Tuple[float, float, float]] = None,
        look_at_relative: Optional[Tuple[float, float, float]] = (1.0, 0, 0.0),
        look_at_world: Optional[Tuple[float, float, float]] = None,
        rpy_deg: Optional[Tuple[float, float, float]] = None,
        rot_matrix_3x3: Optional[Union[np.ndarray, List[List[float]]]] = None,
        look_distance_m: float = 2.0,
        max_cloud_height_m: Optional[float] = None,
        resolution: Tuple[int, int] = (768, 768),  # (height, width)
        include_robot: bool = True,
        view: bool = True,
        save: bool = True,
        save_dir: str = "artifacts/chora",
        filename: Optional[str] = "debug.png",
        # HUD options
        hud: Optional[List[HudElement]] = None,
        hud_warnings: bool = True,
        hud_frame_info: bool = True,
        hud_stats: bool = False,
    ) -> RenderResult:
        """
        Renders a view of my 3D 'chora' from my virtual `theoria` camera.

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

        # Reset per-render state
        self._clear_render_warnings()
        self._resolve_world_frame()

        # Need a recent synchronized frame
        ok = self._wait_for_frame(timeout_s=2.0)
        if not ok:
            raise RuntimeError("Timed out waiting for synchronized camera frame.")

        with self._frame_lock:
            pc_msg = self._latest_pc
            rgb_msg = self._latest_rgb
            info_msg = self._latest_info

        if pc_msg is None or rgb_msg is None or info_msg is None:
            raise RuntimeError("Camera streams not ready (missing synchronized triple).")

        # TF can lag on the very first call (buffer not yet populated).
        # Retry a few times with short sleeps before giving up.
        _TF_MAX_RETRIES = 5
        _TF_RETRY_DELAY_S = 0.4
        camera_world = look_world = None
        for attempt in range(_TF_MAX_RETRIES):
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
                break  # Success
            except RuntimeError as e:
                if "TF failed" in str(e) and attempt < _TF_MAX_RETRIES - 1:
                    print(
                        f"[chora] TF not ready (attempt {attempt + 1}/"
                        f"{_TF_MAX_RETRIES}), retrying in "
                        f"{_TF_RETRY_DELAY_S}s..."
                    )
                    time.sleep(_TF_RETRY_DELAY_S)
                    continue
                raise  # Final attempt or non-TF error — propagate

        live_pcd_map = self._build_live_colored_pcd_map(
            pc_msg=pc_msg,
            rgb_msg=rgb_msg,
            info_msg=info_msg,
            max_cloud_height_m=max_cloud_height_m,
        )

        # All Open3D OffscreenRenderer work MUST happen on the dedicated
        # render thread (Filament thread-affinity requirement).
        img_bgr, snapshot = self._run_on_render_thread(
            lambda: self._render_scene(
                live_pcd_map=live_pcd_map,
                camera_world_pos=camera_world,
                look_at_world_pos=look_world,
                width=width,
                height=height,
                include_robot=include_robot,
            )
        )

        # Cache snapshot by id
        with self._renders_lock:
            self._renders[snapshot.render_id] = snapshot

        # ---- HUD overlay (runs on caller thread — no Filament involved) ----
        all_hud: List[HudElement] = []
        # System-generated HUD (warnings, frame info, stats)
        all_hud.extend(self._build_system_hud(
            snapshot,
            show_warnings=hud_warnings,
            show_frame_info=hud_frame_info,
            show_stats=hud_stats,
        ))
        # User-supplied HUD elements
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
            source="chora",
            # save=save,
            # view=view,
            timestamp=snapshot.timestamp,
            resolution=(height, width),
            photo_id=None,
            path=None,
            pose=pose,
            meta={
                "render_id": snapshot.render_id,
                "camera_world_pos": snapshot.camera_world_pos.tolist(),
                "look_at_world_pos": snapshot.look_at_world_pos.tolist(),
                "view_matrix": snapshot.view_matrix.tolist(),
                "projection_matrix": snapshot.projection_matrix.tolist(),
                "ray_infinity_distance_m": snapshot.ray_infinity_distance_m,
                "snapshot": snapshot,  # intentionally store rich object for later raycasts
            },
        )

        """        
        if save:
            os.makedirs(save_dir, exist_ok=True)
            if filename is None:
                filename = f"chora_{snapshot.render_id}.png"
            path = os.path.join(save_dir, filename)

            ok = cv2.imwrite(path, img_bgr) if _HAS_CV2 else False
            if ok:
                result.path = path
                result.photo_id = snapshot.render_id"""

        if save or view:
            result.save(view=view)

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
        Projects a 2D pixel from a `chora` render back into the 3D world.

        This is the inverse of `render()`. It takes a `RenderResult` and a
        pixel coordinate (in my native 0-1000 normalized format) and shoots
        a virtual ray from the camera through that pixel. It returns a
        `RaycastHit` object describing the first thing the ray intersects
        in the 3D scene (the point cloud, the floor, my own body, etc.).

        Args:
            render: The `RenderResult` object from a previous `render()` call,
                or the string `render_id` from its `.meta` dictionary.
            yx: A `(y, x)` tuple of the pixel to cast from. Coordinates must
                be in my standard 0-1000 normalized space.
            include_floor: If True, the ray can hit the floor plane.
            include_astra: If True, the ray can hit the live point cloud.
            include_robot: If True, the ray can hit my own 3D model.

        Returns:
            A `RaycastHit` dataclass object containing:
            - `.hit`: A string like 'floor', 'astra_cloud', 'robot', or 'infinity'.
            - `.world_point`: The (x, y, z) map coordinate of the intersection.
            - `.distance_m`: The distance from the virtual camera to the hit point.
            - `.floor_state`: If the hit was 'floor', indicates if the map area is
            'map_open', 'map_occupied', or 'unmapped'.

        Note to self:
            This function is the bridge from planning to action. It turns a
            visual intention ("I want to go *there*") into a concrete, actionable
            navigation goal.

            Example workflow:
            ```python
            # 1. Get a top-down view of the area in front of me.
            rr = logos.chora.render(camera_pos_relative=[0, 0, 2.5], look_at_relative=[1.5, 0, 0])
            # 2. Visually identify a clear spot in the middle of the image.
            target_pixel = (500, 500) # (y, x)
            # 3. Get the world coordinate for that spot.
            hit = logos.chora.raycast(rr, target_pixel)
            # 4. If it's a safe spot on the floor, navigate to it.
            if hit.hit == 'floor' and hit.floor_state == 'map_open':
                x, y, z = hit.world_point
                logos.nav.go_to_abs(x, y)
            ```
            The `hit.hit` result is crucial. Hitting 'astra_cloud' or 'robot'
            means my chosen path is likely obstructed. Hitting 'floor' is a good
            sign. Hitting 'infinity' means the path is clear in that direction.

            TODO: I could use this for more than just navigation goals. By
            performing multiple raycasts, I can measure the size of objects,
            check for line-of-sight to a coordinate, or calculate the width of
            a clear path through a doorway, all without physically moving.
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

        # Objects first? No: we'll choose closest hit among all categories.
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
                if not obj.raycast_visible:
                    continue
                if obj.kind == "pointcloud":
                    pts = np.asarray(obj.geometry.points)
                    hit = self._intersect_ray_with_pointcloud(
                        ray_origin,
                        ray_dir,
                        pts,
                        hit_radius_m=float(self.settings["point_hit_radius"]),
                    )
                    if hit is not None:
                        dist, pt = hit
                        hits.append((dist, f"object:{obj.name}", pt, {}))
                elif obj.kind == "mesh":
                    hit = self._intersect_ray_with_mesh_moller_trumbore(ray_origin, ray_dir, obj.geometry)
                    if hit is not None:
                        dist, pt = hit
                        hits.append((dist, f"object:{obj.name}", pt, {}))

        if include_robot and snapshot.robot_mesh is not None:
            hit = self._intersect_ray_with_mesh_moller_trumbore(ray_origin, ray_dir, snapshot.robot_mesh)
            if hit is not None:
                dist, pt = hit
                hits.append((dist, "robot", pt, {}))

        if include_floor:
            hit = self._intersect_ray_with_floor(ray_origin, ray_dir, z_plane=0.0)
            if hit is not None:
                dist, pt = hit
                floor_state = self._floor_state_at(float(pt[0]), float(pt[1]))
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

        # Infinity: return a far point along the ray so the caller can still "place" it if desired.
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

_CHORA_SINGLETON: Optional[Chora] = None
_CHORA_LOCK = threading.Lock()


def get_chora() -> Chora:
    global _CHORA_SINGLETON
    with _CHORA_LOCK:
        if _CHORA_SINGLETON is None:
            _CHORA_SINGLETON = Chora()
        return _CHORA_SINGLETON


# Public convenience functions (so Logos can call logos.chora.render(...) directly)

@api_call(default_verbosity=Verbosity.ACK)
def render(*args, **kwargs) -> RenderResult:
    return get_chora().render(*args, **kwargs)


@api_call(default_verbosity=Verbosity.ACK)
def raycast(*args, **kwargs) -> RaycastHit:
    return get_chora().raycast(*args, **kwargs)



__all__ = [
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
    "Chora",
    "get_chora",
    "render",
    "raycast",
]