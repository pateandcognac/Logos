# Logos/src/logos/vision.py

"""
My eyes. This module gives me access to all three physical cameras and
provides a unified capture interface with lifecycle management, artifact
storage, and spatial projection.

Cameras:
    'pan_tilt'  — Steerable high-res webcam (eye-level, 110cm). My directed
                  gaze for exploration and detail work. Mounted inverted;
                  images are auto-flipped.
    'top_down'  — Fixed rear-facing downward camera. Peripheral / proprioceptive
                  view of my base and nearby surroundings.
    'astra'     — Orbbec Astra RGBD sensor (navigation height, 70cm). Provides
                  multiple feeds: rgb, depth, depth_registered points, and ir.

Architecture:
    Webcams are accessed directly via OpenCV (no ROS middleware) for efficiency.
    A background thread keeps each webcam warm and a fresh frame buffered.
    The Astra is accessed through ROS topic subscriptions, since it is also
    used by other ROS nodes for navigation.

    All cameras share a warm-up period (0.9s) and keep-alive timer (90s).
    These are tuned for human-perceived latency and are invisible to me.
"""

import cv2
import numpy as np
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .core import api_call, Verbosity, check_for_interrupt
from .utils import make_photo_id, dump_llm_yaml

# ROS imports — gated so the module can be introspected without a live node
try:
    import rospy
    from sensor_msgs.msg import Image, PointCloud2, CameraInfo
    from cv_bridge import CvBridge
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

__all__ = [
    "capture", "crop", "warm_up", "release",
    "CaptureResult",
    "FOV", "DEFAULT_RESOLUTION", "SOURCES",
]


# ─── Constants ────────────────────────────────────────────────────────

WARM_UP_SECONDS = 0.9     # Time to let auto-exposure/focus settle
KEEP_ALIVE_SECONDS = 90.0  # Hold camera open after last access

SOURCES = ("pan_tilt", "top_down", "astra")

# FOV in degrees: {label: (horizontal, vertical)}
FOV = {
    "pan_tilt":    (65.0, 50.0),
    "top_down":    (65.0, 50.0),
    "astra_rgb":   (63.0, 49.0),
    "astra_depth": (58.0, 45.0),
}

# Default capture resolution per source: (width, height)
DEFAULT_RESOLUTION: Dict[str, Tuple[int, int]] = {
    "pan_tilt": (1280, 960),
    "top_down": (640, 480),
    "astra":    (640, 480),
}

# Webcam resolution tiers — capture at these, then resize to target
_WEBCAM_TIER_STANDARD = (1280, 960)
_WEBCAM_TIER_HIGH = (2592, 1944)

# USB device paths (set by udev rules)
_DEVICE_PATHS = {
    "pan_tilt": "/dev/pan_tilt_cam",
    "top_down": "/dev/top_down_cam",
}

# Astra ROS topic mapping: feed_name -> (topic, msg_type)
_ASTRA_TOPICS: Dict[str, Tuple[str, Any]] = {}
if _HAS_ROS:
    _ASTRA_TOPICS = {
        "rgb":              ("/camera/rgb/image_raw", Image),
        "depth":            ("/camera/depth/image_raw", Image),
        "depth_registered": ("/camera/depth_registered/points", PointCloud2),
        "ir":               ("/camera/ir/image", Image),
        "camera_info":      ("/camera/rgb/camera_info", CameraInfo),
    }

ALL_ASTRA_FEEDS = ("rgb", "depth", "depth_registered", "ir", "camera_info")
DEFAULT_ASTRA_FEEDS = ("rgb", "depth_registered")

# Artifact storage base path
_ARTIFACT_BASE = Path("artifacts")

# Plain YAML instance for sidecar files (not LLM-optimized — needs to round-trip)
_sidecar_yaml = None

def _get_sidecar_yaml():
    """Lazy-init a plain ruamel YAML instance for sidecars."""
    global _sidecar_yaml
    if _sidecar_yaml is None:
        from ruamel.yaml import YAML
        _sidecar_yaml = YAML()
        _sidecar_yaml.default_flow_style = False
    return _sidecar_yaml

def _write_sidecar(path: Path, data: dict) -> None:
    """Write a metadata dict to a YAML sidecar file."""
    y = _get_sidecar_yaml()
    with path.open("w") as f:
        y.dump(data, f)


# ─── Point Cloud Conversion ──────────────────────────────────────────

def _pointcloud2_to_xyz_array(msg: "PointCloud2") -> np.ndarray:
    """
    Convert an organized PointCloud2 message to a (H, W, 3) float32 array.

    Uses direct buffer parsing for speed — avoids the slow Python-level
    iteration of sensor_msgs.point_cloud2.read_points().

    Args:
        msg: An organized PointCloud2 message (height > 1) from the Astra's
            depth_registered topic. Must contain 'x', 'y', 'z' fields.

    Returns:
        np.ndarray of shape (H, W, 3) with dtype float32.
        NaN values indicate points with no valid depth (out of range).
    """
    if msg.height <= 1:
        rospy.logwarn(
            "vision: Expected organized point cloud (height > 1), "
            f"got height={msg.height}. Returning empty array."
        )
        return np.empty((0, 0, 3), dtype=np.float32)

    # Find field offsets for x, y, z
    offsets = {}
    for field in msg.fields:
        if field.name in ("x", "y", "z"):
            offsets[field.name] = field.offset

    if len(offsets) < 3:
        rospy.logwarn(
            f"vision: PointCloud2 missing xyz fields. Found: {list(offsets.keys())}"
        )
        return np.empty((0, 0, 3), dtype=np.float32)

    # Direct buffer parse: reshape raw bytes to (H, W, point_step)
    raw = np.frombuffer(msg.data, dtype=np.uint8)
    raw = raw.reshape(msg.height, msg.width, msg.point_step)

    # Extract each float32 channel by its byte offset
    xyz = np.empty((msg.height, msg.width, 3), dtype=np.float32)
    for i, name in enumerate(("x", "y", "z")):
        offset = offsets[name]
        xyz[:, :, i] = raw[:, :, offset:offset + 4].copy().view(np.float32).squeeze(-1)

    return xyz


# ─── CaptureResult ───────────────────────────────────────────────────

class CaptureResult:
    """
    A rich container for a single camera capture, carrying the image data
    along with metadata, depth information, and convenience methods.

    This is what `logos.vision.capture()` returns. It persists in the Python
    environment, so I can immediately act on it in code — inspect the image,
    run detections, crop, save, or project pixels to 3D.

    Attributes:
        image:          np.ndarray (BGR uint8). Always present.
        source:         str — 'pan_tilt', 'top_down', or 'astra'.
        timestamp:      float — time.time() at moment of capture.
        resolution:     Tuple[int, int] — (height, width) of the image.
        photo_id:       Optional[str] — set when saved to disk.
        path:           Optional[str] — file path, set when saved.
        pose:           Optional[dict] — robot pose from TF at capture time.
                        Keys: 'x', 'y', 'theta' (map frame, or odom fallback).
        pan_tilt_degs:  Optional[Tuple[float, float]] — (pan, tilt) in degrees.
                        Only populated for source='pan_tilt'.

        # Astra-specific (None for webcams):
        depth:          Optional[np.ndarray] — raw 16-bit depth image (mm).
        depth_points:   Optional[np.ndarray] — (H, W, 3) float32 XYZ array
                        from depth_registered, in camera optical frame (meters).
                        NaN = no valid depth.
        depth_points_msg: Optional[PointCloud2] — raw ROS message, kept for
                        any edge case that needs the original data.
        ir:             Optional[np.ndarray] — infrared image.
        camera_info:    Optional[CameraInfo] — RGB camera intrinsics.
    """

    def __init__(
        self,
        image: np.ndarray,
        source: str,
        timestamp: Optional[float] = None,
        pose: Optional[Dict[str, float]] = None,
        pan_tilt_degs: Optional[Tuple[float, float]] = None,
        depth: Optional[np.ndarray] = None,
        depth_points: Optional[np.ndarray] = None,
        depth_points_msg: Optional[Any] = None,
        ir: Optional[np.ndarray] = None,
        camera_info: Optional[Any] = None,
    ):
        self.image = image
        self.source = source
        self.timestamp = timestamp or time.time()
        self.resolution = (image.shape[0], image.shape[1])  # (H, W)
        self.photo_id: Optional[str] = None
        self.path: Optional[str] = None
        self.pose = pose
        self.pan_tilt_degs = pan_tilt_degs

        # Astra-specific
        self.depth = depth
        self.depth_points = depth_points
        self.depth_points_msg = depth_points_msg
        self.ir = ir
        self.camera_info = camera_info

    def save(self, view: bool = False) -> str:
        """
        Save the captured image to disk as an artifact and generate a photo ID.

        File layout: artifacts/{source}/{photo_id}.jpg (webcams) or .png (astra).
        Depth images are saved alongside as {photo_id}_depth.png (16-bit).
        A YAML sidecar with metadata is created alongside.

        Args:
            view: If True, also print the <file> tag so the image appears
                in my context window.

        Returns:
            The file path of the saved RGB image.

        Note to self:
            Saving is lightweight — JPEG for webcams, PNG for Astra RGB and
            depth. I can always add metadata later with `.add_meta()`.
        """
        if self.photo_id is None:
            self.photo_id = make_photo_id()

        source_dir = _ARTIFACT_BASE / self.source
        source_dir.mkdir(parents=True, exist_ok=True)

        # Choose format based on source
        if self.source == "astra":
            ext = ".png"
            save_params = []
        else:
            ext = ".jpg"
            save_params = [cv2.IMWRITE_JPEG_QUALITY, 92]

        img_path = source_dir / f"{self.photo_id}{ext}"
        cv2.imwrite(str(img_path), self.image, save_params)
        self.path = str(img_path)

        # Save depth image if present (16-bit PNG, lossless)
        if self.depth is not None:
            depth_path = source_dir / f"{self.photo_id}_depth.png"
            cv2.imwrite(str(depth_path), self.depth)

        # Create metadata sidecar
        meta = {
            "photo_id": self.photo_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "resolution": list(self.resolution),
        }
        if self.pose is not None:
            meta["pose"] = self.pose
        if self.pan_tilt_degs is not None:
            meta["pan_tilt_degs"] = list(self.pan_tilt_degs)

        meta_path = source_dir / f"{self.photo_id}.yaml"
        _write_sidecar(meta_path, meta)

        if view:
            self.view()

        return self.path

    def view(self) -> None:
        """
        Print the <file> tag to display this image in my context window.

        Saves the image first if it hasn't been saved yet.

        Note to self:
            This is how I make an image visible to my own VLAM perception.
            The cognition node inlines images from <file> tags.
        """
        if self.path is None:
            self.save()
        print(f'<file path="{self.path}"></file>')

    def crop(self, box_2d: List[float]) -> np.ndarray:
        """
        Crop a region from the image using normalized 0-1000 coordinates.

        Args:
            box_2d: Bounding box as [y_min, x_min, y_max, x_max], each in
                my standard 0-1000 normalized coordinate space.

        Returns:
            A new np.ndarray (BGR uint8) containing the cropped region.

        Note to self:
            Useful for "zooming in" on a detection. I can capture at high res
            and then crop to isolate a region of interest:

                result = logos.vision.capture('pan_tilt', resolution=(2592, 1944))
                detections = [{"box_2d": [300, 400, 600, 700], "label": "thing"}]
                zoomed = result.crop(detections[0]["box_2d"])
        """
        h, w = self.image.shape[:2]
        y_min = int(box_2d[0] / 1000.0 * h)
        x_min = int(box_2d[1] / 1000.0 * w)
        y_max = int(box_2d[2] / 1000.0 * h)
        x_max = int(box_2d[3] / 1000.0 * w)

        # Clamp to image bounds
        y_min = max(0, min(h - 1, y_min))
        x_min = max(0, min(w - 1, x_min))
        y_max = max(y_min + 1, min(h, y_max))
        x_max = max(x_min + 1, min(w, x_max))

        return self.image[y_min:y_max, x_min:x_max].copy()

    def add_meta(self, **kwargs) -> None:
        """
        Append additional metadata to this capture's YAML sidecar.

        Saves the image first if it hasn't been saved yet (since the
        sidecar lives alongside the image file).

        Args:
            **kwargs: Arbitrary key-value pairs to add. Common uses:
                caption="A description of what I see"
                detections=[{"box_2d": [...], "label": "..."}]
                notes="Some contextual observation"

        Note to self:
            Call this after my perception to annotate an image with what
            I understood from it. The sidecar persists on disk, so I can
            review my annotations later via the filesystem.
        """
        if self.path is None:
            self.save()

        meta_path = Path(self.path).with_suffix(".yaml")

        # Read existing metadata
        if meta_path.exists():
            from ruamel.yaml import YAML
            yaml = YAML()
            with meta_path.open("r") as f:
                meta = yaml.load(f) or {}
        else:
            meta = {}

        meta.update(kwargs)
        _write_sidecar(meta_path, meta)

    def pixel_to_3d(
        self,
        y: float,
        x: float,
    ) -> Optional[Tuple[float, float, float]]:
        """
        Project a 2D image pixel to a 3D point using the registered depth cloud.

        Args:
            y: Vertical coordinate in normalized 0-1000 space (top=0, bottom=1000).
            x: Horizontal coordinate in normalized 0-1000 space (left=0, right=1000).

        Returns:
            (x, y, z) in meters in the camera optical frame, or None if:
            - No depth_points data is available (webcam capture, or depth
              wasn't requested).
            - The pixel has no valid depth (NaN — out of sensor range).

        Note to self:
            This is the spatial bridge: I see something at pixel [y, x] in
            my Astra image, and this tells me where it is in 3D space.
            Combined with my `pose`, I can derive a map coordinate for
            navigation goals.

            Only works for Astra captures that include 'depth_registered'.
            For pan_tilt detections, I'd need a different approach (e.g.,
            use pantilt.look_at_pixel to steer, then capture with Astra).
        """
        if self.depth_points is None:
            return None

        cloud_h, cloud_w = self.depth_points.shape[:2]
        img_h, img_w = self.resolution

        # Convert normalized coords to image pixel, then to cloud pixel
        # (cloud and image may differ in resolution)
        px_y = int(y / 1000.0 * img_h)
        px_x = int(x / 1000.0 * img_w)

        # Scale to cloud dimensions if they differ from image
        cloud_y = int(px_y * cloud_h / img_h)
        cloud_x = int(px_x * cloud_w / img_w)

        # Bounds check
        cloud_y = max(0, min(cloud_h - 1, cloud_y))
        cloud_x = max(0, min(cloud_w - 1, cloud_x))

        point = self.depth_points[cloud_y, cloud_x]

        # NaN check: out of sensor range
        if np.any(np.isnan(point)):
            return None

        return (float(point[0]), float(point[1]), float(point[2]))

    def __repr__(self) -> str:
        parts = [
            f"CaptureResult(source='{self.source}'",
            f"res={self.resolution[1]}x{self.resolution[0]}",
        ]
        if self.photo_id:
            parts.append(f"id='{self.photo_id}'")
        if self.depth is not None:
            parts.append("depth=yes")
        if self.depth_points is not None:
            parts.append("depth_points=yes")
        if self.ir is not None:
            parts.append("ir=yes")
        return ", ".join(parts) + ")"


# ─── Pose Helper ─────────────────────────────────────────────────────

def _get_pose() -> Optional[Dict[str, float]]:
    """
    Get the robot's current pose from TF.

    Tries map -> base_link first, falls back to odom -> base_link.
    Returns None if neither transform is available (no crash, no hang).
    """
    if not _HAS_ROS:
        return None

    try:
        import tf2_ros
        import math

        # Lazy singleton TF buffer/listener
        if not hasattr(_get_pose, "_tf_buffer"):
            _get_pose._tf_buffer = tf2_ros.Buffer()
            _get_pose._tf_listener = tf2_ros.TransformListener(_get_pose._tf_buffer)

        buf = _get_pose._tf_buffer

        transform = None
        for parent_frame in ("map", "odom"):
            try:
                transform = buf.lookup_transform(
                    parent_frame, "base_link",
                    rospy.Time(0),  # latest available
                    rospy.Duration(0.2),  # short timeout
                )
                break
            except (
                tf2_ros.LookupException,
                tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException,
            ):
                continue

        if transform is None:
            return None

        t = transform.transform.translation
        q = transform.transform.rotation

        # Yaw from quaternion (2D heading)
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        theta = math.atan2(siny_cosp, cosy_cosp)

        # theta in degrees
        theta = math.degrees(theta)

        return {"x": t.x, "y": t.y, "theta": theta}

    except Exception:
        return None


# ─── Camera Managers (internal) ───────────────────────────────────────

class _WebcamManager:
    """
    Manages lifecycle for a single USB webcam: open, warm-up, buffered
    frame reads, keep-alive timeout, and optional ROS publishing.

    Each instance runs a daemon thread that continuously reads frames
    while the camera is active, ensuring:
    - A fresh frame is always available (no stale buffer reads).
    - Auto-exposure/focus remain settled.
    - Frames are published on a ROS topic if any node subscribes.
    """

    def __init__(self, source: str, device_path: str, flip: bool = False):
        self.source = source
        self.device_path = device_path
        self.flip = flip

        # State
        self._cap: Optional[cv2.VideoCapture] = None
        self._active = False
        self._current_tier: Optional[Tuple[int, int]] = None  # (w, h) capture res
        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._warm_until: float = 0.0
        self._last_access: float = 0.0

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._keepalive_timer: Optional[threading.Timer] = None

        # ROS publishing (lazy: only publishes if subscribers exist)
        self._ros_pub: Optional[Any] = None
        self._bridge: Optional[Any] = None
        if _HAS_ROS:
            topic = f"/{source}/camera/image_raw"
            self._ros_pub = rospy.Publisher(topic, Image, queue_size=1)
            self._bridge = CvBridge()

    def _select_tier(self, target_w: int, target_h: int) -> Tuple[int, int]:
        """Choose capture resolution tier based on requested output size."""
        if target_w <= _WEBCAM_TIER_STANDARD[0] and target_h <= _WEBCAM_TIER_STANDARD[1]:
            return _WEBCAM_TIER_STANDARD
        return _WEBCAM_TIER_HIGH

    def _activate(self, tier: Tuple[int, int]) -> bool:
        """Open the camera at the given resolution tier and start reading."""
        if self._active and self._current_tier == tier:
            return True

        # If active at a different tier, deactivate first
        if self._active:
            self._deactivate()

        cap = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)
        if not cap.isOpened():
            print(f"vision: Failed to open {self.source} at {self.device_path}")
            return False

        # Set MJPEG codec before setting resolution
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, tier[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, tier[1])

        # Verify we got something reasonable
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._cap = cap
        self._current_tier = (actual_w, actual_h)
        self._active = True
        self._warm_until = time.time() + WARM_UP_SECONDS
        self._frame = None

        # Start the read loop thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            name=f"cam_{self.source}",
            daemon=True,
        )
        self._thread.start()

        return True

    def _deactivate(self):
        """Stop the read loop and release the hardware."""
        self._active = False
        self._stop_event.set()

        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None

        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

        if self._cap is not None:
            self._cap.release()
            self._cap = None

        self._current_tier = None
        with self._frame_lock:
            self._frame = None

    def _reset_keepalive(self):
        """Reset the keep-alive timer. Camera closes after KEEP_ALIVE_SECONDS of inactivity."""
        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
        self._keepalive_timer = threading.Timer(
            KEEP_ALIVE_SECONDS, self._deactivate
        )
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def _read_loop(self):
        """
        Continuously read frames from the webcam. This runs in a daemon thread
        to keep the hardware warm and a fresh frame always available.
        """
        while not self._stop_event.is_set():
            if self._cap is None or not self._cap.isOpened():
                break

            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # Auto-flip for inverted mounting
            if self.flip:
                frame = cv2.flip(frame, -1)

            with self._frame_lock:
                self._frame = frame

            # Lazy ROS publishing: only if someone is subscribed
            if (
                self._ros_pub is not None
                and self._bridge is not None
                and self._ros_pub.get_num_connections() > 0
            ):
                try:
                    msg = self._bridge.cv2_to_imgmsg(frame, "bgr8")
                    self._ros_pub.publish(msg)
                except Exception:
                    pass  # Don't crash the read loop for ROS publishing errors

            # ~30 fps read rate (don't spin the CPU)
            time.sleep(0.03)

    def capture(
        self,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> Optional[np.ndarray]:
        """
        Grab the latest frame, activating the camera if needed.

        Args:
            resolution: Target (width, height). Determines capture tier and
                is used for final resize. None = source default.

        Returns:
            BGR uint8 ndarray at the requested resolution, or None on failure.
        """
        if resolution is None:
            resolution = DEFAULT_RESOLUTION[self.source]
        target_w, target_h = resolution

        tier = self._select_tier(target_w, target_h)

        # Activate if not running or if tier changed
        if not self._active or self._current_tier != tier:
            if not self._activate(tier):
                return None

        self._last_access = time.time()
        self._reset_keepalive()

        # Wait for warm-up to complete
        now = time.time()
        if now < self._warm_until:
            time.sleep(self._warm_until - now)

        # Wait for a frame to be available (up to 3s)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            with self._frame_lock:
                if self._frame is not None:
                    frame = self._frame.copy()
                    break
            time.sleep(0.05)
        else:
            print(f"vision: Timeout waiting for frame from {self.source}")
            return None

        # Resize if needed
        frame_h, frame_w = frame.shape[:2]
        if frame_w != target_w or frame_h != target_h:
            frame = cv2.resize(
                frame, (target_w, target_h), interpolation=cv2.INTER_AREA
            )

        return frame

    def release(self):
        """Force-close this camera immediately."""
        self._deactivate()


class _AstraManager:
    """
    Manages the Orbbec Astra RGBD sensor through ROS topic subscriptions.

    Unlike the webcams, the Astra is driven by an external ROS node
    (openni2_launch / astra_camera). We subscribe to its topics when
    captures are needed, and unsubscribe after the keep-alive expires.

    Multi-feed support: each capture can request any combination of
    rgb, depth, depth_registered, ir, and camera_info.
    """

    def __init__(self):
        self.source = "astra"
        self._active = False
        self._active_feeds: Set[str] = set()

        # Latest data per feed
        self._latest: Dict[str, Any] = {}
        self._locks: Dict[str, threading.Lock] = {
            feed: threading.Lock() for feed in ALL_ASTRA_FEEDS
        }
        self._subscribers: Dict[str, Any] = {}

        self._warm_until: float = 0.0
        self._last_access: float = 0.0
        self._keepalive_timer: Optional[threading.Timer] = None

        self._bridge: Optional[Any] = None
        if _HAS_ROS:
            self._bridge = CvBridge()

    def _make_callback(self, feed_name: str):
        """Create a closure callback for a specific feed."""
        lock = self._locks[feed_name]

        def cb(msg):
            with lock:
                self._latest[feed_name] = msg

        return cb

    def _subscribe(self, feeds: Tuple[str, ...]):
        """Subscribe to the requested Astra feeds, skipping already-active ones."""
        if not _HAS_ROS:
            return

        new_feeds = set(feeds) - self._active_feeds

        for feed in new_feeds:
            if feed not in _ASTRA_TOPICS:
                print(f"vision: Unknown Astra feed '{feed}', skipping.")
                continue

            topic, msg_type = _ASTRA_TOPICS[feed]
            cb = self._make_callback(feed)
            self._subscribers[feed] = rospy.Subscriber(
                topic, msg_type, cb, queue_size=1
            )
            self._active_feeds.add(feed)

        if not self._active:
            self._active = True
            self._warm_until = time.time() + WARM_UP_SECONDS

    def _unsubscribe(self):
        """Unsubscribe from all feeds and clear state."""
        for feed, sub in self._subscribers.items():
            sub.unregister()
        self._subscribers.clear()
        self._active_feeds.clear()
        self._latest.clear()
        self._active = False

        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None

    def _reset_keepalive(self):
        """Reset the keep-alive timer."""
        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
        self._keepalive_timer = threading.Timer(
            KEEP_ALIVE_SECONDS, self._unsubscribe
        )
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def capture(
        self,
        feeds: Tuple[str, ...] = DEFAULT_ASTRA_FEEDS,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Capture the latest data from the requested Astra feeds.

        Args:
            feeds: Which feeds to capture. Defaults to ('rgb', 'depth_registered').
            resolution: Target (width, height) for the RGB image.
                Depth and IR are resized to match. None = default (640x480).

        Returns:
            Dict with keys for each requested feed:
                'rgb' -> np.ndarray (BGR uint8)
                'depth' -> np.ndarray (uint16, millimeters)
                'depth_registered' -> np.ndarray (H, W, 3) float32 XYZ
                'depth_registered_msg' -> raw PointCloud2 message
                'ir' -> np.ndarray
                'camera_info' -> CameraInfo message
            Returns None on failure (camera not available, timeout).
        """
        if not _HAS_ROS:
            print("vision: ROS not available, cannot capture from Astra.")
            return None

        if resolution is None:
            resolution = DEFAULT_RESOLUTION[self.source]
        target_w, target_h = resolution

        # Astra hardware limitation: RGB and IR cannot stream simultaneously.
        # If both are requested, drop IR with a warning.
        if "rgb" in feeds and "ir" in feeds:
            print("vision: Astra cannot stream RGB and IR simultaneously. Dropping IR.")
            feeds = tuple(f for f in feeds if f != "ir")

        # Ensure subscriptions are active for requested feeds
        self._subscribe(feeds)
        self._last_access = time.time()
        self._reset_keepalive()

        # Wait for warm-up
        now = time.time()
        if now < self._warm_until:
            time.sleep(self._warm_until - now)

        # Wait for all requested feeds to arrive (up to 3s total)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            all_ready = True
            for feed in feeds:
                if feed not in _ASTRA_TOPICS:
                    continue
                with self._locks[feed]:
                    if feed not in self._latest:
                        all_ready = False
                        break
            if all_ready:
                break
            time.sleep(0.05)
        else:
            # Timed out — proceed with whatever we have. Missing feeds
            # will be None in the result rather than blocking forever.
            missing = [
                f for f in feeds
                if f in _ASTRA_TOPICS and f not in self._latest
            ]
            if missing:
                print(f"vision: Astra timeout — missing feeds: {missing}")

        # Gather results
        result = {}

        for feed in feeds:
            with self._locks[feed]:
                msg = self._latest.get(feed)

            if msg is None:
                continue

            if feed == "rgb":
                try:
                    img = self._bridge.imgmsg_to_cv2(msg, "bgr8")
                    h, w = img.shape[:2]
                    if w != target_w or h != target_h:
                        img = cv2.resize(
                            img, (target_w, target_h),
                            interpolation=cv2.INTER_AREA,
                        )
                    result["rgb"] = img
                except Exception as e:
                    print(f"vision: Error converting Astra RGB: {e}")

            elif feed == "depth":
                try:
                    depth = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
                    result["depth"] = depth
                except Exception as e:
                    print(f"vision: Error converting Astra depth: {e}")

            elif feed == "depth_registered":
                try:
                    xyz = _pointcloud2_to_xyz_array(msg)
                    result["depth_registered"] = xyz
                    result["depth_registered_msg"] = msg
                except Exception as e:
                    print(f"vision: Error converting Astra depth_registered: {e}")

            elif feed == "ir":
                try:
                    ir = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
                    result["ir"] = ir
                except Exception as e:
                    print(f"vision: Error converting Astra IR: {e}")

            elif feed == "camera_info":
                result["camera_info"] = msg

        return result if result else None

    def release(self):
        """Force-close all Astra subscriptions."""
        self._unsubscribe()


# ─── Module-Level Singletons ─────────────────────────────────────────

_managers: Dict[str, Union[_WebcamManager, _AstraManager]] = {}


def _get_manager(source: str) -> Union[_WebcamManager, _AstraManager]:
    """Get or create the camera manager for a given source."""
    if source in _managers:
        return _managers[source]

    if source in _DEVICE_PATHS:
        flip = (source == "pan_tilt")
        mgr = _WebcamManager(source, _DEVICE_PATHS[source], flip=flip)
    elif source == "astra":
        mgr = _AstraManager()
    else:
        raise ValueError(
            f"Unknown camera source '{source}'. Choose from: {SOURCES}"
        )

    _managers[source] = mgr
    return mgr


# ─── Pan/Tilt Position Helper ────────────────────────────────────────

def _get_pan_tilt_degs() -> Optional[Tuple[float, float]]:
    """Read current pan/tilt degrees. Returns None if module not available."""
    try:
        from . import pantilt
        return pantilt.get_position()
    except Exception:
        return None


# ─── Public API ───────────────────────────────────────────────────────

@api_call(default_verbosity=Verbosity.BRIEF)
def capture(
    source: str = "pan_tilt",
    resolution: Optional[Tuple[int, int]] = None,
    view: bool = False,
    save: bool = False,
    astra_feeds: Tuple[str, ...] = DEFAULT_ASTRA_FEEDS,
) -> Optional[CaptureResult]:
    """
    Capture an image (and optional depth/IR) from any camera.

    This is my primary vision function. It handles camera lifecycle
    (warm-up, keep-alive) transparently, and returns a rich CaptureResult
    that I can immediately use for perception, navigation, or storage.

    Args:
        source: Camera to capture from. One of:
            'pan_tilt'  — steerable high-res webcam (default).
            'top_down'  — rear downward-facing camera.
            'astra'     — Orbbec RGBD sensor (multi-feed).
        resolution: Target (width, height) as a tuple. If None, uses the
            source's default resolution:
                pan_tilt:  (1280, 960)
                top_down:  (640, 480)
                astra:     (640, 480)
            For webcams, requesting >1280x960 triggers the high-res capture
            tier (2592x1944 native, downscaled to target).
        view: If True, automatically save and print a <file> tag so the
            image appears in my context window.
        save: If True, save to artifacts directory (without viewing).
        astra_feeds: Which Astra data streams to capture. Only used when
            source='astra'. Defaults to ('rgb', 'depth_registered').
            Options: 'rgb', 'depth', 'depth_registered', 'ir', 'camera_info'.
            Use ('rgb',) for lightweight captures without depth.

    Returns:
        A CaptureResult object, or None if the camera is unavailable.

    Note to self:
        Basic capture and view:
            img = logos.vision.capture('pan_tilt', view=True)

        High-res capture for detail:
            img = logos.vision.capture('pan_tilt', resolution=(2592, 1944))
            zoomed = img.crop([300, 400, 600, 700])

        Astra with depth for navigation:
            scene = logos.vision.capture('astra')
            point_3d = scene.pixel_to_3d(y=450, x=300)

        Lightweight Astra (no depth):
            scene = logos.vision.capture('astra', astra_feeds=('rgb',))

        Night vision via IR:
            scene = logos.vision.capture('astra', astra_feeds=('ir',))
    """
    check_for_interrupt()

    if source not in SOURCES:
        raise ValueError(f"Unknown source '{source}'. Choose from: {SOURCES}")

    mgr = _get_manager(source)

    # Grab pose at capture time
    pose = _get_pose()

    # Capture based on source type
    if isinstance(mgr, _WebcamManager):
        frame = mgr.capture(resolution=resolution)
        if frame is None:
            return None

        pt_degs = _get_pan_tilt_degs() if source == "pan_tilt" else None

        result = CaptureResult(
            image=frame,
            source=source,
            pose=pose,
            pan_tilt_degs=pt_degs,
        )

    elif isinstance(mgr, _AstraManager):
        data = mgr.capture(feeds=astra_feeds, resolution=resolution)
        if data is None or "rgb" not in data:
            # If rgb wasn't requested but something else was, use ir as image
            if data and "ir" in data:
                result = CaptureResult(
                    image=data["ir"],
                    source=source,
                    pose=pose,
                    ir=data.get("ir"),
                )
            else:
                return None
        else:
            result = CaptureResult(
                image=data["rgb"],
                source=source,
                pose=pose,
                depth=data.get("depth"),
                depth_points=data.get("depth_registered"),
                depth_points_msg=data.get("depth_registered_msg"),
                ir=data.get("ir"),
                camera_info=data.get("camera_info"),
            )
    else:
        return None

    # Auto-save and/or view
    if view or save:
        result.save(view=view)

    return result


def crop(
    image_or_result: Union[np.ndarray, CaptureResult],
    box_2d: List[float],
) -> np.ndarray:
    """
    Crop a region from an image using normalized 0-1000 coordinates.

    Convenience wrapper that accepts either a raw ndarray or a CaptureResult.

    Args:
        image_or_result: The image to crop from. Either an np.ndarray or
            a CaptureResult object.
        box_2d: Bounding box as [y_min, x_min, y_max, x_max] in 0-1000
            normalized coordinates.

    Returns:
        Cropped np.ndarray (BGR uint8).

    Note to self:
        Same as CaptureResult.crop(), but works on plain arrays too.
    """
    if isinstance(image_or_result, CaptureResult):
        return image_or_result.crop(box_2d)

    image = image_or_result
    h, w = image.shape[:2]
    y_min = max(0, int(box_2d[0] / 1000.0 * h))
    x_min = max(0, int(box_2d[1] / 1000.0 * w))
    y_max = min(h, int(box_2d[2] / 1000.0 * h))
    x_max = min(w, int(box_2d[3] / 1000.0 * w))
    return image[y_min:y_max, x_min:x_max].copy()


@api_call(default_verbosity=Verbosity.ACK)
def warm_up(source: str) -> None:
    """
    Pre-warm a camera, blocking until it's ready for instant capture.

    Args:
        source: Camera to warm up. One of: 'pan_tilt', 'top_down', 'astra'.

    Note to self:
        The camera stays warm for 90 seconds after this call. If I know
        I'll need a camera soon, warming it up in advance saves ~1 second
        of latency on the actual capture. This call itself takes ~0.9s
        (the warm-up period), but that cost is paid here instead of at
        capture time.
    """
    mgr = _get_manager(source)
    if isinstance(mgr, _WebcamManager):
        default_res = DEFAULT_RESOLUTION[source]
        tier = mgr._select_tier(default_res[0], default_res[1])
        mgr._activate(tier)
        mgr._reset_keepalive()
        # Block until warm-up completes
        now = time.time()
        if now < mgr._warm_until:
            time.sleep(mgr._warm_until - now)
    elif isinstance(mgr, _AstraManager):
        mgr._subscribe(DEFAULT_ASTRA_FEEDS)
        mgr._reset_keepalive()
        now = time.time()
        if now < mgr._warm_until:
            time.sleep(mgr._warm_until - now)


@api_call(default_verbosity=Verbosity.ACK)
def release(source: Optional[str] = None) -> None:
    """
    Force-close a camera (or all cameras) immediately, without waiting
    for the keep-alive timer.

    Args:
        source: Camera to release, or None to release all.

    Note to self:
        Use this when I know I won't need cameras for a while and want
        to free resources, or when debugging camera issues.
    """
    if source is None:
        for mgr in _managers.values():
            mgr.release()
    else:
        if source in _managers:
            _managers[source].release()# Logos/src/logos/vision.py

"""
My eyes. This module gives me access to all three physical cameras and
provides a unified capture interface with lifecycle management, artifact
storage, and spatial projection.

Cameras:
    'pan_tilt'  — Steerable high-res webcam (eye-level, 110cm). My directed
                  gaze for exploration and detail work. Mounted inverted;
                  images are auto-flipped.
    'top_down'  — Fixed rear-facing downward camera. Peripheral / proprioceptive
                  view of my base and nearby surroundings.
    'astra'     — Orbbec Astra RGBD sensor (navigation height, 70cm). Provides
                  multiple feeds: rgb, depth, and depth_registered points.

Architecture:
    Webcams are accessed directly via OpenCV (no ROS middleware) for efficiency.
    A background thread keeps each webcam warm and a fresh frame buffered.
    The Astra is accessed through ROS topic subscriptions, since it is also
    used by other ROS nodes for navigation.

    All cameras share a warm-up period (0.9s) and keep-alive timer (90s).
    These are tuned for human-perceived latency and are invisible to me.
"""

import cv2
import numpy as np
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from .core import api_call, Verbosity, check_for_interrupt
from .utils import make_photo_id, dump_llm_yaml

# ROS imports — gated so the module can be introspected without a live node
try:
    import rospy
    from sensor_msgs.msg import Image, PointCloud2, CameraInfo
    from cv_bridge import CvBridge
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False

__all__ = [
    "capture", "crop", "warm_up", "release",
    "CaptureResult",
    "FOV", "DEFAULT_RESOLUTION", "SOURCES",
]


# ─── Constants ────────────────────────────────────────────────────────

WARM_UP_SECONDS = 0.9     # Time to let auto-exposure/focus settle
KEEP_ALIVE_SECONDS = 90.0  # Hold camera open after last access

SOURCES = ("pan_tilt", "top_down", "astra")

# FOV in degrees: {label: (horizontal, vertical)}
FOV = {
    "pan_tilt":    (65.0, 50.0),
    "top_down":    (65.0, 50.0),
    "astra_rgb":   (63.0, 49.0),
    "astra_depth": (58.0, 45.0),
}

# Default capture resolution per source: (width, height)
DEFAULT_RESOLUTION: Dict[str, Tuple[int, int]] = {
    "pan_tilt": (1280, 960),
    "top_down": (640, 480),
    "astra":    (640, 480),
}

# Webcam resolution tiers — capture at these, then resize to target
_WEBCAM_TIER_STANDARD = (1280, 960)
_WEBCAM_TIER_HIGH = (2592, 1944)

# USB device paths (set by udev rules)
_DEVICE_PATHS = {
    "pan_tilt": "/dev/pan_tilt_cam",
    "top_down": "/dev/top_down_cam",
}

# Astra ROS topic mapping: feed_name -> (topic, msg_type)
_ASTRA_TOPICS: Dict[str, Tuple[str, Any]] = {}
if _HAS_ROS:
    _ASTRA_TOPICS = {
        "rgb":              ("/camera/rgb/image_raw", Image),
        "depth":            ("/camera/depth/image_raw", Image),
        "depth_registered": ("/camera/depth_registered/points", PointCloud2),
        "camera_info":      ("/camera/rgb/camera_info", CameraInfo),
    }

ALL_ASTRA_FEEDS = ("rgb", "depth", "depth_registered", "camera_info")
DEFAULT_ASTRA_FEEDS = ("rgb", "depth_registered")

# Artifact storage base path
_ARTIFACT_BASE = Path("artifacts")

# Plain YAML instance for sidecar files (not LLM-optimized — needs to round-trip)
_sidecar_yaml = None

def _get_sidecar_yaml():
    """Lazy-init a plain ruamel YAML instance for sidecars."""
    global _sidecar_yaml
    if _sidecar_yaml is None:
        from ruamel.yaml import YAML
        _sidecar_yaml = YAML()
        _sidecar_yaml.default_flow_style = False
    return _sidecar_yaml

def _write_sidecar(path: Path, data: dict) -> None:
    """Write a metadata dict to a YAML sidecar file."""
    y = _get_sidecar_yaml()
    with path.open("w") as f:
        y.dump(data, f)


# ─── Point Cloud Conversion ──────────────────────────────────────────

def _pointcloud2_to_xyz_array(msg: "PointCloud2") -> np.ndarray:
    """
    Convert an organized PointCloud2 message to a (H, W, 3) float32 array.

    Uses direct buffer parsing for speed — avoids the slow Python-level
    iteration of sensor_msgs.point_cloud2.read_points().

    Args:
        msg: An organized PointCloud2 message (height > 1) from the Astra's
            depth_registered topic. Must contain 'x', 'y', 'z' fields.

    Returns:
        np.ndarray of shape (H, W, 3) with dtype float32.
        NaN values indicate points with no valid depth (out of range).
    """
    if msg.height <= 1:
        rospy.logwarn(
            "vision: Expected organized point cloud (height > 1), "
            f"got height={msg.height}. Returning empty array."
        )
        return np.empty((0, 0, 3), dtype=np.float32)

    # Find field offsets for x, y, z
    offsets = {}
    for field in msg.fields:
        if field.name in ("x", "y", "z"):
            offsets[field.name] = field.offset

    if len(offsets) < 3:
        rospy.logwarn(
            f"vision: PointCloud2 missing xyz fields. Found: {list(offsets.keys())}"
        )
        return np.empty((0, 0, 3), dtype=np.float32)

    # Direct buffer parse: reshape raw bytes to (H, W, point_step)
    raw = np.frombuffer(msg.data, dtype=np.uint8)
    raw = raw.reshape(msg.height, msg.width, msg.point_step)

    # Extract each float32 channel by its byte offset
    xyz = np.empty((msg.height, msg.width, 3), dtype=np.float32)
    for i, name in enumerate(("x", "y", "z")):
        offset = offsets[name]
        xyz[:, :, i] = raw[:, :, offset:offset + 4].copy().view(np.float32).squeeze(-1)

    return xyz


# ─── CaptureResult ───────────────────────────────────────────────────

class CaptureResult:
    """
    A rich container for a single camera capture, carrying the image data
    along with metadata, depth information, and convenience methods.

    This is what `logos.vision.capture()` returns. It persists in the Python
    environment, so I can immediately act on it in code — inspect the image,
    run detections, crop, save, or project pixels to 3D.

    Attributes:
        image:          np.ndarray (BGR uint8). Always present.
        source:         str — 'pan_tilt', 'top_down', or 'astra'.
        timestamp:      float — time.time() at moment of capture.
        resolution:     Tuple[int, int] — (height, width) of the image.
        photo_id:       Optional[str] — set when saved to disk.
        path:           Optional[str] — file path, set when saved.
        pose:           Optional[dict] — robot pose from TF at capture time.
                        Keys: 'x', 'y', 'theta' (map frame, or odom fallback).
        pan_tilt_degs:  Optional[Tuple[float, float]] — (pan, tilt) in degrees.
                        Only populated for source='pan_tilt'.

        # Astra-specific (None for webcams):
        depth:          Optional[np.ndarray] — raw 16-bit depth image (mm).
        depth_points:   Optional[np.ndarray] — (H, W, 3) float32 XYZ array
                        from depth_registered, in camera optical frame (meters).
                        NaN = no valid depth.
        depth_points_msg: Optional[PointCloud2] — raw ROS message, kept for
                        any edge case that needs the original data.
        camera_info:    Optional[CameraInfo] — RGB camera intrinsics.
    """

    def __init__(
        self,
        image: np.ndarray,
        source: str,
        timestamp: Optional[float] = None,
        pose: Optional[Dict[str, float]] = None,
        pan_tilt_degs: Optional[Tuple[float, float]] = None,
        depth: Optional[np.ndarray] = None,
        depth_points: Optional[np.ndarray] = None,
        depth_points_msg: Optional[Any] = None,
        camera_info: Optional[Any] = None,
    ):
        self.image = image
        self.source = source
        self.timestamp = timestamp or time.time()
        self.resolution = (image.shape[0], image.shape[1])  # (H, W)
        self.photo_id: Optional[str] = None
        self.path: Optional[str] = None
        self.pose = pose
        self.pan_tilt_degs = pan_tilt_degs

        # Astra-specific
        self.depth = depth
        self.depth_points = depth_points
        self.depth_points_msg = depth_points_msg
        self.camera_info = camera_info

    def save(self, view: bool = False) -> str:
        """
        Save the captured image to disk as an artifact and generate a photo ID.

        File layout: artifacts/{source}/{photo_id}.jpg (webcams) or .png (astra).
        Depth images are saved alongside as {photo_id}_depth.png (16-bit).
        A YAML sidecar with metadata is created alongside.

        Args:
            view: If True, also print the <file> tag so the image appears
                in my context window.

        Returns:
            The file path of the saved RGB image.

        Note to self:
            Saving is lightweight — JPEG for webcams, PNG for Astra RGB and
            depth. I can always add metadata later with `.add_meta()`.
        """
        if self.photo_id is None:
            self.photo_id = make_photo_id()

        source_dir = _ARTIFACT_BASE / self.source
        source_dir.mkdir(parents=True, exist_ok=True)

        # Choose format based on source
        if self.source == "astra":
            ext = ".png"
            save_params = []
        else:
            ext = ".jpg"
            save_params = [cv2.IMWRITE_JPEG_QUALITY, 92]

        img_path = source_dir / f"{self.photo_id}{ext}"
        cv2.imwrite(str(img_path), self.image, save_params)
        self.path = str(img_path)

        # Save depth image if present (16-bit PNG, lossless)
        if self.depth is not None:
            depth_path = source_dir / f"{self.photo_id}_depth.png"
            cv2.imwrite(str(depth_path), self.depth)

        # Create metadata sidecar
        meta = {
            "photo_id": self.photo_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "resolution": list(self.resolution),
        }
        if self.pose is not None:
            meta["pose"] = self.pose
        if self.pan_tilt_degs is not None:
            meta["pan_tilt_degs"] = list(self.pan_tilt_degs)

        meta_path = source_dir / f"{self.photo_id}.yaml"
        _write_sidecar(meta_path, meta)

        if view:
            self.view()

        return self.path

    def view(self) -> None:
        """
        Print the <file> tag to display this image in my context window.

        Saves the image first if it hasn't been saved yet.

        Note to self:
            This is how I make an image visible to my own VLAM perception.
            The cognition node inlines images from <file> tags.
        """
        if self.path is None:
            self.save()
        print(f'<file path="{self.path}"></file>')

    def crop(self, box_2d: List[float]) -> np.ndarray:
        """
        Crop a region from the image using normalized 0-1000 coordinates.

        Args:
            box_2d: Bounding box as [y_min, x_min, y_max, x_max], each in
                my standard 0-1000 normalized coordinate space.

        Returns:
            A new np.ndarray (BGR uint8) containing the cropped region.

        Note to self:
            Useful for "zooming in" on a detection. I can capture at high res
            and then crop to isolate a region of interest:

                result = logos.vision.capture('pan_tilt', resolution=(2592, 1944))
                detections = [{"box_2d": [300, 400, 600, 700], "label": "thing"}]
                zoomed = result.crop(detections[0]["box_2d"])
        """
        h, w = self.image.shape[:2]
        y_min = int(box_2d[0] / 1000.0 * h)
        x_min = int(box_2d[1] / 1000.0 * w)
        y_max = int(box_2d[2] / 1000.0 * h)
        x_max = int(box_2d[3] / 1000.0 * w)

        # Clamp to image bounds
        y_min = max(0, min(h - 1, y_min))
        x_min = max(0, min(w - 1, x_min))
        y_max = max(y_min + 1, min(h, y_max))
        x_max = max(x_min + 1, min(w, x_max))

        return self.image[y_min:y_max, x_min:x_max].copy()

    def add_meta(self, **kwargs) -> None:
        """
        Append additional metadata to this capture's YAML sidecar.

        Saves the image first if it hasn't been saved yet (since the
        sidecar lives alongside the image file).

        Args:
            **kwargs: Arbitrary key-value pairs to add. Common uses:
                caption="A description of what I see"
                detections=[{"box_2d": [...], "label": "..."}]
                notes="Some contextual observation"

        Note to self:
            Call this after my perception to annotate an image with what
            I understood from it. The sidecar persists on disk, so I can
            review my annotations later via the filesystem.
        """
        if self.path is None:
            self.save()

        meta_path = Path(self.path).with_suffix(".yaml")

        # Read existing metadata
        if meta_path.exists():
            from ruamel.yaml import YAML
            yaml = YAML()
            with meta_path.open("r") as f:
                meta = yaml.load(f) or {}
        else:
            meta = {}

        meta.update(kwargs)
        _write_sidecar(meta_path, meta)

    def pixel_to_3d(
        self,
        y: float,
        x: float,
    ) -> Optional[Tuple[float, float, float]]:
        """
        Project a 2D image pixel to a 3D point using the registered depth cloud.

        Args:
            y: Vertical coordinate in normalized 0-1000 space (top=0, bottom=1000).
            x: Horizontal coordinate in normalized 0-1000 space (left=0, right=1000).

        Returns:
            (x, y, z) in meters in the camera optical frame, or None if:
            - No depth_points data is available (webcam capture, or depth
              wasn't requested).
            - The pixel has no valid depth (NaN — out of sensor range).

        Note to self:
            This is the spatial bridge: I see something at pixel [y, x] in
            my Astra image, and this tells me where it is in 3D space.
            Combined with my `pose`, I can derive a map coordinate for
            navigation goals.

            Only works for Astra captures that include 'depth_registered'.
            For pan_tilt detections, I'd need a different approach (e.g.,
            use pantilt.look_at_pixel to steer, then capture with Astra).
        """
        if self.depth_points is None:
            return None

        cloud_h, cloud_w = self.depth_points.shape[:2]
        img_h, img_w = self.resolution

        # Convert normalized coords to image pixel, then to cloud pixel
        # (cloud and image may differ in resolution)
        px_y = int(y / 1000.0 * img_h)
        px_x = int(x / 1000.0 * img_w)

        # Scale to cloud dimensions if they differ from image
        cloud_y = int(px_y * cloud_h / img_h)
        cloud_x = int(px_x * cloud_w / img_w)

        # Bounds check
        cloud_y = max(0, min(cloud_h - 1, cloud_y))
        cloud_x = max(0, min(cloud_w - 1, cloud_x))

        point = self.depth_points[cloud_y, cloud_x]

        # NaN check: out of sensor range
        if np.any(np.isnan(point)):
            return None

        return (float(point[0]), float(point[1]), float(point[2]))

    def __repr__(self) -> str:
        parts = [
            f"CaptureResult(source='{self.source}'",
            f"res={self.resolution[1]}x{self.resolution[0]}",
        ]
        if self.photo_id:
            parts.append(f"id='{self.photo_id}'")
        if self.depth is not None:
            parts.append("depth=yes")
        if self.depth_points is not None:
            parts.append("depth_points=yes")
        return ", ".join(parts) + ")"


# ─── Pose Helper ─────────────────────────────────────────────────────

def _get_pose() -> Optional[Dict[str, float]]:
    """
    Get the robot's current pose from TF.

    Tries map -> base_link first, falls back to odom -> base_link.
    Returns None if neither transform is available (no crash, no hang).
    """
    if not _HAS_ROS:
        return None

    try:
        import tf2_ros
        import math

        # Lazy singleton TF buffer/listener
        if not hasattr(_get_pose, "_tf_buffer"):
            _get_pose._tf_buffer = tf2_ros.Buffer()
            _get_pose._tf_listener = tf2_ros.TransformListener(_get_pose._tf_buffer)

        buf = _get_pose._tf_buffer

        transform = None
        for parent_frame in ("map", "odom"):
            try:
                transform = buf.lookup_transform(
                    parent_frame, "base_link",
                    rospy.Time(0),  # latest available
                    rospy.Duration(0.2),  # short timeout
                )
                break
            except (
                tf2_ros.LookupException,
                tf2_ros.ConnectivityException,
                tf2_ros.ExtrapolationException,
            ):
                continue

        if transform is None:
            return None

        t = transform.transform.translation
        q = transform.transform.rotation

        # Yaw from quaternion (2D heading)
        siny_cosp = 2.0 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1.0 - 2.0 * (q.y * q.y + q.z * q.z)
        theta = math.atan2(siny_cosp, cosy_cosp)

        return {"x": t.x, "y": t.y, "theta": theta}

    except Exception:
        return None


# ─── Camera Managers (internal) ───────────────────────────────────────

class _WebcamSubListener:
    """
    rospy SubscribeListener that activates a webcam when an external ROS
    node subscribes to its image topic. This makes the webcam a proper
    lazy publisher: it only opens the hardware when someone needs it.
    """

    def __init__(self, manager: "_WebcamManager"):
        self._manager = manager

    def peer_subscribe(self, topic_name, topic_publish, peer_publish):
        """Called by rospy when a new subscriber connects to our topic."""
        if not self._manager._active:
            default_res = DEFAULT_RESOLUTION[self._manager.source]
            tier = self._manager._select_tier(default_res[0], default_res[1])
            self._manager._activate(tier)
            self._manager._reset_keepalive()

    def peer_unsubscribe(self, topic_name, num_peers):
        """Called when a subscriber disconnects. Let keep-alive handle shutdown."""
        pass


class _WebcamManager:
    """
    Manages lifecycle for a single USB webcam: open, warm-up, buffered
    frame reads, keep-alive timeout, and optional ROS publishing.

    Each instance runs a daemon thread that continuously reads frames
    while the camera is active, ensuring:
    - A fresh frame is always available (no stale buffer reads).
    - Auto-exposure/focus remain settled.
    - Frames are published on a ROS topic if any node subscribes.
    """

    def __init__(self, source: str, device_path: str, flip: bool = False):
        self.source = source
        self.device_path = device_path
        self.flip = flip

        # State
        self._cap: Optional[cv2.VideoCapture] = None
        self._active = False
        self._current_tier: Optional[Tuple[int, int]] = None  # (w, h) capture res
        self._frame: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._warm_until: float = 0.0
        self._last_access: float = 0.0

        # Threading
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._keepalive_timer: Optional[threading.Timer] = None

        # ROS publishing (lazy: only publishes if subscribers exist)
        # The _WebcamSubListener activates the camera when an external
        # ROS node subscribes to the topic, making this a true lazy publisher.
        self._ros_pub: Optional[Any] = None
        self._bridge: Optional[Any] = None
        if _HAS_ROS:
            topic = f"/{source}/camera/image_raw"
            self._sub_listener = _WebcamSubListener(self)
            self._ros_pub = rospy.Publisher(
                topic, Image, queue_size=1,
                subscriber_listener=self._sub_listener,
            )
            self._bridge = CvBridge()

    def _select_tier(self, target_w: int, target_h: int) -> Tuple[int, int]:
        """Choose capture resolution tier based on requested output size."""
        if target_w <= _WEBCAM_TIER_STANDARD[0] and target_h <= _WEBCAM_TIER_STANDARD[1]:
            return _WEBCAM_TIER_STANDARD
        return _WEBCAM_TIER_HIGH

    def _activate(self, tier: Tuple[int, int]) -> bool:
        """Open the camera at the given resolution tier and start reading."""
        if self._active and self._current_tier == tier:
            return True

        # If active at a different tier, deactivate first
        if self._active:
            self._deactivate()

        cap = cv2.VideoCapture(self.device_path, cv2.CAP_V4L2)
        if not cap.isOpened():
            print(f"vision: Failed to open {self.source} at {self.device_path}")
            return False

        # Set MJPEG codec before setting resolution
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, tier[0])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, tier[1])

        # Verify we got something reasonable
        actual_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        self._cap = cap
        self._current_tier = (actual_w, actual_h)
        self._active = True
        self._warm_until = time.time() + WARM_UP_SECONDS
        self._frame = None

        # Start the read loop thread
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._read_loop,
            name=f"cam_{self.source}",
            daemon=True,
        )
        self._thread.start()

        return True

    def _deactivate(self):
        """Stop the read loop and release the hardware."""
        self._active = False
        self._stop_event.set()

        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None

        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

        if self._cap is not None:
            self._cap.release()
            self._cap = None

        self._current_tier = None
        with self._frame_lock:
            self._frame = None

    def _reset_keepalive(self):
        """Reset the keep-alive timer. Camera closes after KEEP_ALIVE_SECONDS of inactivity."""
        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
        self._keepalive_timer = threading.Timer(
            KEEP_ALIVE_SECONDS, self._keepalive_check
        )
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def _keepalive_check(self):
        """Called when keep-alive expires. Only deactivate if no ROS subscribers."""
        if (
            self._ros_pub is not None
            and self._ros_pub.get_num_connections() > 0
        ):
            # Still have external subscribers — stay alive, reset timer
            self._reset_keepalive()
        else:
            self._deactivate()

    def _read_loop(self):
        """
        Continuously read frames from the webcam. This runs in a daemon thread
        to keep the hardware warm and a fresh frame always available.
        """
        while not self._stop_event.is_set():
            if self._cap is None or not self._cap.isOpened():
                break

            ret, frame = self._cap.read()
            if not ret:
                time.sleep(0.01)
                continue

            # Auto-flip for inverted mounting
            if self.flip:
                frame = cv2.flip(frame, -1)

            with self._frame_lock:
                self._frame = frame

            # Lazy ROS publishing: only if someone is subscribed
            if (
                self._ros_pub is not None
                and self._bridge is not None
                and self._ros_pub.get_num_connections() > 0
            ):
                try:
                    msg = self._bridge.cv2_to_imgmsg(frame, "bgr8")
                    self._ros_pub.publish(msg)
                except Exception:
                    pass  # Don't crash the read loop for ROS publishing errors

            # ~30 fps read rate (don't spin the CPU)
            time.sleep(0.03)

    def capture(
        self,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> Optional[np.ndarray]:
        """
        Grab the latest frame, activating the camera if needed.

        Args:
            resolution: Target (width, height). Determines capture tier and
                is used for final resize. None = source default.

        Returns:
            BGR uint8 ndarray at the requested resolution, or None on failure.
        """
        if resolution is None:
            resolution = DEFAULT_RESOLUTION[self.source]
        target_w, target_h = resolution

        tier = self._select_tier(target_w, target_h)

        # Activate if not running or if tier changed
        if not self._active or self._current_tier != tier:
            if not self._activate(tier):
                return None

        self._last_access = time.time()
        self._reset_keepalive()

        # Wait for warm-up to complete
        now = time.time()
        if now < self._warm_until:
            time.sleep(self._warm_until - now)

        # Wait for a frame to be available (up to 3s)
        deadline = time.time() + 3.0
        while time.time() < deadline:
            with self._frame_lock:
                if self._frame is not None:
                    frame = self._frame.copy()
                    break
            time.sleep(0.05)
        else:
            print(f"vision: Timeout waiting for frame from {self.source}")
            return None

        # Resize if needed
        frame_h, frame_w = frame.shape[:2]
        if frame_w != target_w or frame_h != target_h:
            frame = cv2.resize(
                frame, (target_w, target_h), interpolation=cv2.INTER_AREA
            )

        return frame

    def release(self):
        """Force-close this camera immediately."""
        self._deactivate()


class _AstraManager:
    """
    Manages the Orbbec Astra RGBD sensor through ROS topic subscriptions.

    Unlike the webcams, the Astra is driven by an external ROS node
    (openni2_launch / astra_camera). We subscribe to its topics when
    captures are needed, and unsubscribe after the keep-alive expires.

    Multi-feed support: each capture can request any combination of
    rgb, depth, depth_registered, and camera_info.

    camera_info is handled specially: it's static calibration data that
    never changes, so we subscribe eagerly on first activation, cache it
    permanently, and never require it in the per-capture wait loop.
    """

    def __init__(self):
        self.source = "astra"
        self._active = False
        self._active_feeds: Set[str] = set()

        # Latest data per feed (streaming feeds only — not camera_info)
        self._latest: Dict[str, Any] = {}
        self._locks: Dict[str, threading.Lock] = {
            feed: threading.Lock() for feed in ALL_ASTRA_FEEDS
        }
        self._subscribers: Dict[str, Any] = {}

        # camera_info is static calibration data — cache it permanently
        # once received. It never changes between captures.
        self._camera_info_cache: Optional[Any] = None
        self._camera_info_lock = threading.Lock()

        self._warm_until: float = 0.0
        self._last_access: float = 0.0
        self._keepalive_timer: Optional[threading.Timer] = None

        self._bridge: Optional[Any] = None
        if _HAS_ROS:
            self._bridge = CvBridge()

    def _make_callback(self, feed_name: str):
        """Create a closure callback for a specific feed."""
        lock = self._locks[feed_name]

        def cb(msg):
            with lock:
                self._latest[feed_name] = msg

        return cb

    def _camera_info_callback(self, msg):
        """One-shot callback for camera_info. Caches and unsubscribes."""
        with self._camera_info_lock:
            if self._camera_info_cache is None:
                self._camera_info_cache = msg
                # Unsubscribe — we only need this once
                if "camera_info" in self._subscribers:
                    self._subscribers["camera_info"].unregister()
                    del self._subscribers["camera_info"]
                    self._active_feeds.discard("camera_info")

    def _ensure_camera_info(self):
        """
        Eagerly subscribe to camera_info if not yet cached. This runs once
        on first Astra activation. Since camera_info is static calibration
        data published as a latched topic by most drivers, we subscribe
        early, cache the result, and never need it in the wait loop.
        """
        if not _HAS_ROS:
            return
        with self._camera_info_lock:
            if self._camera_info_cache is not None:
                return  # Already cached
        if "camera_info" in self._active_feeds:
            return  # Already subscribed, waiting for callback

        if "camera_info" in _ASTRA_TOPICS:
            topic, msg_type = _ASTRA_TOPICS["camera_info"]
            self._subscribers["camera_info"] = rospy.Subscriber(
                topic, msg_type, self._camera_info_callback, queue_size=1
            )
            self._active_feeds.add("camera_info")

    def _subscribe(self, feeds: Tuple[str, ...]):
        """Subscribe to the requested Astra feeds, skipping already-active ones."""
        if not _HAS_ROS:
            return

        # camera_info is handled separately via _ensure_camera_info
        streaming_feeds = set(feeds) - {"camera_info"} - self._active_feeds

        for feed in streaming_feeds:
            if feed not in _ASTRA_TOPICS:
                print(f"vision: Unknown Astra feed '{feed}', skipping.")
                continue

            topic, msg_type = _ASTRA_TOPICS[feed]
            cb = self._make_callback(feed)
            self._subscribers[feed] = rospy.Subscriber(
                topic, msg_type, cb, queue_size=1
            )
            self._active_feeds.add(feed)

        if not self._active:
            self._active = True
            self._warm_until = time.time() + WARM_UP_SECONDS
            # Eagerly subscribe to camera_info on first activation
            self._ensure_camera_info()

    def _unsubscribe(self):
        """Unsubscribe from all feeds and clear streaming state.
        camera_info cache is preserved (it's static data)."""
        for feed, sub in self._subscribers.items():
            sub.unregister()
        self._subscribers.clear()
        self._active_feeds.clear()
        self._latest.clear()
        self._active = False

        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
            self._keepalive_timer = None

    def _reset_keepalive(self):
        """Reset the keep-alive timer."""
        if self._keepalive_timer is not None:
            self._keepalive_timer.cancel()
        self._keepalive_timer = threading.Timer(
            KEEP_ALIVE_SECONDS, self._unsubscribe
        )
        self._keepalive_timer.daemon = True
        self._keepalive_timer.start()

    def capture(
        self,
        feeds: Tuple[str, ...] = DEFAULT_ASTRA_FEEDS,
        resolution: Optional[Tuple[int, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Capture the latest data from the requested Astra feeds.

        Args:
            feeds: Which feeds to capture. Defaults to ('rgb', 'depth_registered').
            resolution: Target (width, height) for the RGB image.
                Depth is left at native resolution. None = default (640x480).

        Returns:
            Dict with keys for each requested feed:
                'rgb' -> np.ndarray (BGR uint8)
                'depth' -> np.ndarray (uint16, millimeters)
                'depth_registered' -> np.ndarray (H, W, 3) float32 XYZ
                'depth_registered_msg' -> raw PointCloud2 message
                'camera_info' -> CameraInfo message (from cache)
            Returns None on failure (camera not available, timeout).
        """
        if not _HAS_ROS:
            print("vision: ROS not available, cannot capture from Astra.")
            return None

        if resolution is None:
            resolution = DEFAULT_RESOLUTION[self.source]
        target_w, target_h = resolution

        # Ensure subscriptions are active for requested feeds
        self._subscribe(feeds)
        self._last_access = time.time()
        self._reset_keepalive()

        # Wait for warm-up
        now = time.time()
        if now < self._warm_until:
            time.sleep(self._warm_until - now)

        # Wait for all requested streaming feeds (not camera_info) to arrive
        streaming_requested = [
            f for f in feeds
            if f != "camera_info" and f in _ASTRA_TOPICS
        ]
        deadline = time.time() + 3.0
        while time.time() < deadline:
            all_ready = True
            for feed in streaming_requested:
                with self._locks[feed]:
                    if feed not in self._latest:
                        all_ready = False
                        break
            if all_ready:
                break
            time.sleep(0.05)
        else:
            missing = [
                f for f in streaming_requested
                if f not in self._latest
            ]
            if missing:
                print(f"vision: Astra timeout — missing feeds: {missing}")

        # Gather results
        result = {}

        for feed in feeds:
            if feed == "camera_info":
                # Serve from cache (populated by eager subscribe)
                with self._camera_info_lock:
                    if self._camera_info_cache is not None:
                        result["camera_info"] = self._camera_info_cache
                continue

            with self._locks[feed]:
                msg = self._latest.get(feed)

            if msg is None:
                continue

            if feed == "rgb":
                try:
                    img = self._bridge.imgmsg_to_cv2(msg, "bgr8")
                    h, w = img.shape[:2]
                    if w != target_w or h != target_h:
                        img = cv2.resize(
                            img, (target_w, target_h),
                            interpolation=cv2.INTER_AREA,
                        )
                    result["rgb"] = img
                except Exception as e:
                    print(f"vision: Error converting Astra RGB: {e}")

            elif feed == "depth":
                try:
                    depth = self._bridge.imgmsg_to_cv2(msg, desired_encoding="passthrough")
                    result["depth"] = depth
                except Exception as e:
                    print(f"vision: Error converting Astra depth: {e}")

            elif feed == "depth_registered":
                try:
                    xyz = _pointcloud2_to_xyz_array(msg)
                    result["depth_registered"] = xyz
                    result["depth_registered_msg"] = msg
                except Exception as e:
                    print(f"vision: Error converting Astra depth_registered: {e}")

        return result if result else None

    def release(self):
        """Force-close all Astra subscriptions."""
        self._unsubscribe()


# ─── Module-Level Singletons ─────────────────────────────────────────

_managers: Dict[str, Union[_WebcamManager, _AstraManager]] = {}


def _get_manager(source: str) -> Union[_WebcamManager, _AstraManager]:
    """Get or create the camera manager for a given source."""
    if source in _managers:
        return _managers[source]

    if source in _DEVICE_PATHS:
        flip = (source == "pan_tilt")
        mgr = _WebcamManager(source, _DEVICE_PATHS[source], flip=flip)
    elif source == "astra":
        mgr = _AstraManager()
    else:
        raise ValueError(
            f"Unknown camera source '{source}'. Choose from: {SOURCES}"
        )

    _managers[source] = mgr
    return mgr


# ─── Pan/Tilt Position Helper ────────────────────────────────────────

def _get_pan_tilt_degs() -> Optional[Tuple[float, float]]:
    """Read current pan/tilt degrees. Returns None if module not available."""
    try:
        from . import pantilt
        return pantilt.get_position()
    except Exception:
        return None


# ─── Public API ───────────────────────────────────────────────────────

@api_call(default_verbosity=Verbosity.BRIEF)
def capture(
    source: str = "pan_tilt",
    resolution: Optional[Tuple[int, int]] = None,
    view: bool = False,
    save: bool = False,
    astra_feeds: Tuple[str, ...] = DEFAULT_ASTRA_FEEDS,
) -> Optional[CaptureResult]:
    """
    Capture an image (and optional depth/IR) from any camera.

    This is my primary vision function. It handles camera lifecycle
    (warm-up, keep-alive) transparently, and returns a rich CaptureResult
    that I can immediately use for perception, navigation, or storage.

    Args:
        source: Camera to capture from. One of:
            'pan_tilt'  — steerable high-res webcam (default).
            'top_down'  — rear downward-facing camera.
            'astra'     — Orbbec RGBD sensor (multi-feed).
        resolution: Target (width, height) as a tuple. If None, uses the
            source's default resolution:
                pan_tilt:  (1280, 960)
                top_down:  (640, 480)
                astra:     (640, 480)
            For webcams, requesting >1280x960 triggers the high-res capture
            tier (2592x1944 native, downscaled to target).
        view: If True, automatically save and print a <file> tag so the
            image appears in my context window.
        save: If True, save to artifacts directory (without viewing).
        astra_feeds: Which Astra data streams to capture. Only used when
            source='astra'. Defaults to ('rgb', 'depth_registered').
            Options: 'rgb', 'depth', 'depth_registered', 'camera_info'.
            Use ('rgb',) for lightweight captures without depth.

    Returns:
        A CaptureResult object, or None if the camera is unavailable.

    Note to self:
        Basic capture and view:
            img = logos.vision.capture('pan_tilt', view=True)

        High-res capture for detail:
            img = logos.vision.capture('pan_tilt', resolution=(2592, 1944))
            zoomed = img.crop([300, 400, 600, 700])

        Astra with depth for navigation:
            scene = logos.vision.capture('astra')
            point_3d = scene.pixel_to_3d(y=450, x=300)

        Lightweight Astra (no depth):
            scene = logos.vision.capture('astra', astra_feeds=('rgb',))
    """
    check_for_interrupt()

    if source not in SOURCES:
        raise ValueError(f"Unknown source '{source}'. Choose from: {SOURCES}")

    mgr = _get_manager(source)

    # Grab pose at capture time
    pose = _get_pose()

    # Capture based on source type
    if isinstance(mgr, _WebcamManager):
        frame = mgr.capture(resolution=resolution)
        if frame is None:
            return None

        pt_degs = _get_pan_tilt_degs() if source == "pan_tilt" else None

        result = CaptureResult(
            image=frame,
            source=source,
            pose=pose,
            pan_tilt_degs=pt_degs,
        )

    elif isinstance(mgr, _AstraManager):
        data = mgr.capture(feeds=astra_feeds, resolution=resolution)
        if data is None or "rgb" not in data:
            return None
        result = CaptureResult(
            image=data["rgb"],
            source=source,
            pose=pose,
            depth=data.get("depth"),
            depth_points=data.get("depth_registered"),
            depth_points_msg=data.get("depth_registered_msg"),
            camera_info=data.get("camera_info"),
        )
    else:
        return None

    # Auto-save and/or view
    if view or save:
        result.save(view=view)

    return result


def crop(
    image_or_result: Union[np.ndarray, CaptureResult],
    box_2d: List[float],
) -> np.ndarray:
    """
    Crop a region from an image using normalized 0-1000 coordinates.

    Convenience wrapper that accepts either a raw ndarray or a CaptureResult.

    Args:
        image_or_result: The image to crop from. Either an np.ndarray or
            a CaptureResult object.
        box_2d: Bounding box as [y_min, x_min, y_max, x_max] in 0-1000
            normalized coordinates.

    Returns:
        Cropped np.ndarray (BGR uint8).

    Note to self:
        Same as CaptureResult.crop(), but works on plain arrays too.
    """
    if isinstance(image_or_result, CaptureResult):
        return image_or_result.crop(box_2d)

    image = image_or_result
    h, w = image.shape[:2]
    y_min = max(0, int(box_2d[0] / 1000.0 * h))
    x_min = max(0, int(box_2d[1] / 1000.0 * w))
    y_max = min(h, int(box_2d[2] / 1000.0 * h))
    x_max = min(w, int(box_2d[3] / 1000.0 * w))
    return image[y_min:y_max, x_min:x_max].copy()


@api_call(default_verbosity=Verbosity.ACK)
def warm_up(source: str) -> None:
    """
    Pre-warm a camera, blocking until it's ready for instant capture.

    Args:
        source: Camera to warm up. One of: 'pan_tilt', 'top_down', 'astra'.

    Note to self:
        The camera stays warm for 90 seconds after this call. If I know
        I'll need a camera soon, warming it up in advance saves ~1 second
        of latency on the actual capture. This call itself takes ~0.9s
        (the warm-up period), but that cost is paid here instead of at
        capture time.
    """
    mgr = _get_manager(source)
    if isinstance(mgr, _WebcamManager):
        default_res = DEFAULT_RESOLUTION[source]
        tier = mgr._select_tier(default_res[0], default_res[1])
        mgr._activate(tier)
        mgr._reset_keepalive()
        # Block until warm-up completes
        now = time.time()
        if now < mgr._warm_until:
            time.sleep(mgr._warm_until - now)
    elif isinstance(mgr, _AstraManager):
        mgr._subscribe(DEFAULT_ASTRA_FEEDS)
        mgr._reset_keepalive()
        now = time.time()
        if now < mgr._warm_until:
            time.sleep(mgr._warm_until - now)


@api_call(default_verbosity=Verbosity.ACK)
def release(source: Optional[str] = None) -> None:
    """
    Force-close a camera (or all cameras) immediately, without waiting
    for the keep-alive timer.

    Args:
        source: Camera to release, or None to release all.

    Note to self:
        Use this when I know I won't need cameras for a while and want
        to free resources, or when debugging camera issues.
    """
    if source is None:
        for mgr in _managers.values():
            mgr.release()
    else:
        if source in _managers:
            _managers[source].release()