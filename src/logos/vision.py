# src/logos/vision.py

"""
My eyes. This module gives me access to all three physical cameras and provides a unified capture interface with lifecycle management, artifact storage, and spatial projection.

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
import fnmatch
import os
from .core import api_call, Verbosity, check_for_interrupt
from .utils import make_time_id, dump_yaml
from .ros import get_pose
from . import config as logos_config

# ROS imports — gated so the module can be introspected without a live node
try:
    import rospy
    from sensor_msgs.msg import Image, PointCloud2, CameraInfo
    from cv_bridge import CvBridge
    _HAS_ROS = True
except ImportError:
    _HAS_ROS = False



_debug_pubs: Dict[str, Any] = {}
_bridge = None


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

# Default capture resolution per source: (height, width)
DEFAULT_RESOLUTION: Dict[str, Tuple[int, int]] = {
    "pan_tilt": (960, 1280),
    "top_down": (480, 640),
    "astra":    (480, 640),
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
_ARTIFACT_BASE = Path("ipc")

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
                        Keys: 'x', 'y', 'theta_deg' (map frame, or odom fallback).
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
        meta: Optional[Dict[str, Any]] = None,
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
            meta: Optional[Dict[str, Any]] = None,
        ):
        self.image = image
        self.source = source
        # self.timestamp = timestamp or time.time()
        self.timestamp = timestamp or rospy.Time.now().to_sec()
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
        
        # User-defined metadata container
        self.meta = meta or {} 

    def save(
        self, 
        view: bool = False, 
        meta_keys: Optional[List[str]] = None
    ) -> str:
        """
        Save the captured image to disk and generate a photo ID.
        
        Args:
            view: If True, also print the <file> tag.
            meta_keys: If view is True, this list of wildcard patterns defines 
                       which metadata keys are displayed inside the <file> tag.
                       e.g. ['caption', 'det_*', 'pose']
        """
        if self.photo_id is None:
            self.photo_id = make_time_id()

        source_dir = _ARTIFACT_BASE / self.source
        source_dir.mkdir(parents=True, exist_ok=True)

        # [Image saving logic remains the same...]
        if self.source == "astra":
            ext = ".png"
            save_params = []
        else:
            ext = ".jpg"
            save_params = [cv2.IMWRITE_JPEG_QUALITY, 92]

        img_path = source_dir / f"{self.photo_id}{ext}"
        cv2.imwrite(str(img_path), self.image, save_params)
        self.path = str(img_path)

        if self.depth is not None:
            depth_path = source_dir / f"{self.photo_id}_depth.png"
            cv2.imwrite(str(depth_path), self.depth)

        # Compile full metadata (System authoritative + User custom)
        # We start with the existing meta so system keys can overwrite duplicates if necessary
        full_meta = self.meta.copy() # CHANGE: use self.meta
        
        system_meta = {
            "photo_id": self.photo_id,
            "source": self.source,
            "timestamp": self.timestamp,
            "resolution": list(self.resolution),
        }
        if self.pose is not None:
            system_meta["pose"] = self.pose
        if self.pan_tilt_degs is not None:
            system_meta["pan_tilt_degs"] = list(self.pan_tilt_degs)
            
        full_meta.update(system_meta)

        # Update internal meta to reflect the full data saved to disk
        self.meta = full_meta

        meta_path = source_dir / f"{self.photo_id}.yaml"
        _write_sidecar(meta_path, full_meta)

        if view:
            self.view(meta_keys=meta_keys)

        return self.path

    def view(self, meta_keys: Optional[List[str]] = None) -> None:
        """
        Print the <file> tag to display this image in my context window.

        Args:
            meta_keys: Optional list of shell-style wildcard patterns (e.g. 
                       ['caption', 'detections', 'pose*']). keys matching 
                       these patterns will be formatted as YAML inside the tag.
        """
        if self.path is None:
            # If not saved, save it (which will trigger view via recursion if we passed args)
            # But here we just save and then handle the printing ourselves.
            self.save(view=False)
        
        content = ""
        
        if meta_keys and self.meta:
            filtered_meta = {}
            for key, value in self.meta.items():
                for pattern in meta_keys:
                    if fnmatch.fnmatch(key, pattern):
                        filtered_meta[key] = value
                        break # Key matches, move to next key
            
            if filtered_meta:
                # Format using the LLM-optimized YAML dumper
                yaml_str = dump_yaml(filtered_meta)
                content = f"\n{yaml_str}"

        print(f'<file path="{self.path}">{content}</file>')

    def crop(self, box_2d: List[float]) -> "CaptureResult":
        """
        Crop a region from the image using normalized 0-1000 coordinates.

        Args:
            box_2d: Bounding box as [y_min, x_min, y_max, x_max] in 
                my standard 0-1000 normalized coordinate space.

        Returns:
            A new CaptureResult containing the cropped region. Depth and camera 
            intrinsics are intentionally dropped, as cropping invalidates them.

        Note to self:
            Useful for isolating a region of interest. Because it returns a 
            CaptureResult, I can immediately save and view it!
                
                res = logos.vision.capture('pan_tilt')
                zoomed = res.crop([300, 400, 600, 700])
                zoomed.view(meta_keys=["parent_photo_id"])
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

        cropped_img = self.image[y_min:y_max, x_min:x_max].copy()

        # Build metadata for the new crop
        crop_meta = {
            "is_crop": True,
            "crop_box_2d": box_2d,
        }
        if self.photo_id:
            crop_meta["parent_photo_id"] = self.photo_id
            
        # Inherit any user-defined metadata from the parent (optional, but handy)
        for k, v in self.meta.items():
            if k not in crop_meta and k not in ["photo_id", "resolution"]:
                crop_meta[k] = v

        return CaptureResult(
            image=cropped_img,
            source=self.source,
            timestamp=self.timestamp,
            pose=self.pose,
            pan_tilt_degs=self.pan_tilt_degs,
            # Intentionally omitting depth/camera_info to prevent spatial math errors
            meta=crop_meta
        )

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
        # CHANGE: Update the unified meta dictionary directly
        self.meta.update(kwargs)

        # If already saved, update the sidecar file. If not, the metadata
        # will be included the next time .save() is called.
        if self.path is not None:
            meta_path = Path(self.path).with_suffix(".yaml")
            _write_sidecar(meta_path, self.meta)


    def derive_world_coordinate(
        self,
        *args,
        search_radius: int = 3
    ) -> Optional[Tuple[float, float, float]]:
        """
        Projects a normalized 2D location from Astra image into real-world 3D coordinates (map frame).

        Args:
            *args: This can be:
                   - A single list/tuple: `([y, x])` or `([y1, x1, y2, x2])`
                   - Two separate numbers: `(y, x)`
                   - Four separate numbers: `(y1, x1, y2, x2)`
            search_radius: Pixels to search outward if the initial point is NaN.

        Note to self:
            Uses our 0-1000 normalized system.
            For boxes, the center point is calculated.
            I've made this function very flexible. I can pass it a YOLO detection 
            dictionary directly, a box list, or raw coordinates.
            Does *not* work  for pan-tilt images.
            
            Examples:
                # Passing a list (Good for splatting or direct box passing)
                res.derive_world_coordinate(my_box)
                res.derive_world_coordinate(*my_point)
                
                # Passing raw numbers
                res.derive_world_coordinate(500, 500)
        """
        from . import ros

        if self.depth_points is None or self.depth_points_msg is None:
            return None

        # 1. Parse the flexible *args to find our target Y and X
        if len(args) == 1:
            target = args[0]
            if len(target) == 4: # It's a box [y1, x1, y2, x2]
                y, x = (target[0] + target[2]) / 2, (target[1] + target[3]) / 2
            else: # It's a point [y, x]
                y, x = target[0], target[1]
        elif len(args) == 2: # It's raw y, x
            y, x = args[0], args[1]
        elif len(args) == 4: # It's raw y1, x1, y2, x2
            y, x = (args[0] + args[2]) / 2, (args[1] + args[3]) / 2
        else:
            raise ValueError(f"vision: derive_world_coordinate got unexpected arguments: {args}")

        cloud_h, cloud_w = self.depth_points.shape[:2]
        cloud_y, cloud_x = int((y / 1000.0) * cloud_h), int((x / 1000.0) * cloud_w)

        # 2. Spatial Averaging
        valid_points = []
        for dy in range(-search_radius, search_radius + 1):
            for dx in range(-search_radius, search_radius + 1):
                ny, nx = cloud_y + dy, cloud_x + dx
                if 0 <= ny < cloud_h and 0 <= nx < cloud_w:
                    pt = self.depth_points[ny, nx]
                    if not np.any(np.isnan(pt)) and not np.any(pt == 0.0):
                        valid_points.append(pt)

        if not valid_points:
            return None

        avg_pt = np.mean(valid_points, axis=0)
        source_frame = self.depth_points_msg.header.frame_id
        
        return ros.transform_point_to_map(
            x=float(avg_pt[0]), y=float(avg_pt[1]), z=float(avg_pt[2]),
            source_frame=source_frame, timestamp=self.timestamp
        )

    

    def overlay_coordinate_grid(self, rows: int = 3, cols: int = 4) -> None:
        """
        Burn a grid of sampled 3D coordinates directly into an Astra image.

        This leverages the ViT's ability to "read" dense data visually, 
        effectively compressing spatial information into the image tokens rather
        than spending text tokens.

        Displays:
            - Green Dot: Sampling location.
            - C (Cyan): Camera Frame coordinates (X, Y, Z) relative to sensor.
            - M (Orange): Map Frame coordinates (X, Y, Z) absolute.
            - Red Text: invalid/noisy surface (NaN depth).

        Args:
            rows: Number of vertical sample points.
            cols: Number of horizontal sample points.
        """
        if self.depth_points is None:
            print("vision: Cannot overlay grid, no depth data available.")
            return

        h, w = self.image.shape[:2]
        
        # 1. Expand the grid! 
        # Calculate grid using np.linspace to push points closer to edges
        # We'll use a 15% margin to ensure points aren't exactly on the border
        margin_x = int(w * 0.15)
        margin_y = int(h * 0.15)
        
        x_coords = np.linspace(margin_x, w - margin_x, cols, dtype=int)
        y_coords = np.linspace(margin_y, h - margin_y, rows, dtype=int)
        
        from . import ros

        for py in y_coords:
            for px in x_coords:
                # Draw the sampling anchor dot
                cv2.circle(self.image, (px, py), 3, (0, 255, 0), -1)

                # --- Sampling Logic with NaN Search ---
                # Search a small radius if the exact pixel is invalid (NaN)
                sample_pt = None
                search_radius = 4
                
                # Extract the patch
                y1 = max(0, py - search_radius)
                y2 = min(h, py + search_radius + 1)
                x1 = max(0, px - search_radius)
                x2 = min(w, px + search_radius + 1)
                
                patch = self.depth_points[y1:y2, x1:x2]
                
                valid_mask = ~np.isnan(patch).any(axis=2) & (patch[:, :, 2] != 0)
                valid_pts = patch[valid_mask]

                if valid_pts.size > 0:
                    sample_pt = np.median(valid_pts, axis=0)
                
                # --- Text Generation ---
                # We collect the lines and colors to pass to our adaptive drawer
                text_lines = []
                colors = []

                if sample_pt is not None:
                    cx, cy, cz = sample_pt
                    text_lines.append(f"C({cx:.2f}, {cy:.2f}, {cz:.2f})")
                    colors.append((255, 255, 0)) # Cyan
                    
                    map_pt = ros.transform_point_to_map(
                        cx, cy, cz, 
                        self.depth_points_msg.header.frame_id, 
                        self.timestamp
                    )
                    
                    if map_pt:
                        mx, my, mz = map_pt
                        text_lines.append(f"M({mx:.2f}, {my:.2f}, {mz:.2f})")
                        colors.append((0, 165, 255)) # Orange
                    else:
                        text_lines.append("M: TF Error")
                        colors.append((0, 0, 255)) # Red

                else:
                    text_lines.append("NaN")
                    colors.append((0, 0, 255)) # Red
                    
                # Call the adaptive text drawer
                self._draw_adaptive_labels(px, py, text_lines, colors, w, h)

    def _draw_adaptive_labels(self, px: int, py: int, lines: List[str], colors: List[Tuple[int, int, int]], w: int, h: int):
        """Helper to draw multi-line text that adapts to image edges."""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.3
        thickness = 1
        line_spacing = 4
        
        # Calculate the bounding box of our entire text block
        sizes = [cv2.getTextSize(txt, font, font_scale, thickness)[0] for txt in lines]
        max_tw = max(sz[0] for sz in sizes)
        th = sizes[0][1] # height of one line
        total_th = (len(lines) * th) + ((len(lines) - 1) * line_spacing)
        
        # Default position: Centered horizontally, placed slightly below the dot
        start_x = px - (max_tw // 2)
        start_y = py + 10 
        
        # Adaptive X bounds (Push inward if hitting left/right edges)
        pad = 4
        if start_x < pad:
            start_x = pad
        elif start_x + max_tw > w - pad:
            start_x = w - max_tw - pad
            
        # Adaptive Y bounds (If falling off the bottom, flip to above the dot)
        if start_y + total_th > h - pad:
            start_y = py - 10 - total_th
            
        # Draw the lines!
        current_y = start_y + th # cv2.putText origin is the baseline (bottom of text)
        for txt, color in zip(lines, colors):
            # Draw a black outline (stroke) for readability
            cv2.putText(self.image, txt, (start_x, current_y), font, font_scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
            # Draw the colored text on top
            cv2.putText(self.image, txt, (start_x, current_y), font, font_scale, color, thickness, cv2.LINE_AA)
            current_y += th + line_spacing

    def _draw_label_at(self, x: int, y: int, text: str, color: Tuple[int, int, int]):
        """Helper to draw semi-transparent text at a specific pixel."""
        font_scale = 0.3
        thickness = 1
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        
        # Background box
        pad = 2

        """        
        cv2.rectangle(
            self.image, 
            (x - pad, y - th - pad), 
            (x + tw + pad, y + baseline + pad), 
            (0, 0, 0), 
            cv2.FILLED
        )
        
        """
        # Text
        cv2.putText(
            self.image, 
            text, 
            (x, y), 
            font, 
            font_scale, 
            color, 
            thickness, 
            cv2.LINE_AA
        )



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

            if self._active:
                self._deactivate()

            # 1. Resolve the symlink (e.g., /dev/pan_tilt_cam -> /dev/video1)
            real_path = os.path.realpath(self.device_path)
            
            # 2. Extract the integer index (Robust Logic)
            device_indices = []
            try:
                import re
                match = re.search(r'video(\d+)$', real_path)
                if match:
                    idx = int(match.group(1))
                    device_indices.append(idx)
                    # If symlink points to an odd number (video1), 
                    # chances are the stream is at the even number below it (video0).
                    # This fixes the common "Metadata Node" issue in udev rules.
                    if idx % 2 != 0:
                        device_indices.append(idx - 1)
            except Exception:
                pass
                
            # Fallback: if regex failed, try passing the path directly (though your build hates it)
            if not device_indices:
                device_indices.append(real_path)

            # 3. Try to open the identified indices in order
            cap = None
            for device_index in device_indices:
                # print(f"vision: Attempting to open {self.source} at index {device_index}...")
                temp_cap = cv2.VideoCapture(device_index, cv2.CAP_V4L2)
                
                if temp_cap.isOpened():
                    cap = temp_cap
                    # print(f"vision: Success at index {device_index}")
                    break
                else:
                    # print(f"vision: Failed at index {device_index}")
                    pass

            if cap is None or not cap.isOpened():
                print(f"vision: CRITICAL FAILURE to open {self.source} at {real_path}")
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
            resolution: Target (height, width). Determines capture tier and
                is used for final resize. None = source default.

        Returns:
            BGR uint8 ndarray at the requested resolution, or None on failure.
        """
        if resolution is None:
            resolution = DEFAULT_RESOLUTION[self.source]
        target_h, target_w = resolution

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
            resolution: Target (height, width) for the RGB image.
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
        target_h, target_w = resolution

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
        deadline = time.time() + 6.0
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

def get_pan_tilt_degs() -> Optional[Tuple[float, float]]:
    """Read current pan/tilt degrees. Returns None if module not available."""
    try:
        from . import pantilt
        return pantilt.get_angles()
    except Exception:
        return None


# ─── Public API ───────────────────────────────────────────────────────

@api_call(default_verbosity=Verbosity.BRIEF)
def capture(
    source: Optional[str] = None,
    resolution: Optional[Tuple[int, int]] = None,
    view: bool = False,
    save: bool = False,
    astra_feeds: Tuple[str, ...] = DEFAULT_ASTRA_FEEDS,
    meta: Optional[Dict[str, Any]] = None,
    meta_keys: Optional[List[str]] = None, 
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
        resolution: Target (height, width) as a tuple. If None, uses the
            source's default resolution:
                pan_tilt:  (960, 1280)
                top_down:  (480, 640)
                astra:     (480, 640)
            For webcams, requesting >1280x960 triggers the high-res capture
            tier (2592x1944 native, downscaled to target).
        view: If True, automatically save and print a <file> tag so the
            image appears in my context window.
        save: If True, save to ipc directory (without viewing).
        astra_feeds: Which Astra data streams to capture. Only used when
            source='astra'. Defaults to ('rgb', 'depth_registered').
            Options: 'rgb', 'depth', 'depth_registered', 'camera_info'.
            Use ('rgb',) for lightweight captures without depth.
        meta: A dictionary of arbitrary metadata to save immediately 
            into the sidecar YAML (e.g., {'label': 'kitchen_sink'}).
        meta_keys: If view=True, list of keys/wildcards to display 
            inside the <file> tag (e.g. ['label', 'pose', 'pan_tilt_deg']).

    Returns:
        A CaptureResult object, or None if the camera is unavailable.

    Note to self:
        Basic capture and view:
            img = logos.vision.capture('pan_tilt', view=True)

        High-res capture for detail:
            img = logos.vision.capture('pan_tilt', resolution=(1944, 2592))
            zoomed = img.crop([300, 400, 600, 700])

        Astra with depth for navigation:
            scene = logos.vision.capture('astra')
            point_3d = scene.derive_world_coordinate(y=450, x=300)

        Lightweight Astra (no depth):
            scene = logos.vision.capture('astra', astra_feeds=('rgb',))
    """
    check_for_interrupt()

    # 1. Resolve source from Config if not explicitly provided
    vision_cfg = logos_config.merged.get('vision', {})
    source = source or vision_cfg.get('default_source', 'pan_tilt')

    # 2. Resolve resolution from Config if not explicitly provided
    if resolution is None:
        res_cfg = vision_cfg.get('resolutions', {})
        # res_list should be a list like [h, w]
        res_list = res_cfg.get(source)
        if res_list and len(res_list) == 2:
            # YAML gives lists, we need a tuple
            resolution = tuple(res_list)
        else:
            resolution = DEFAULT_RESOLUTION.get(source, (480, 640))

    if source not in SOURCES:
        raise ValueError(f"Unknown source '{source}'. Choose from: {SOURCES}")

    mgr = _get_manager(source)

    # Grab pose at capture time
    pose = get_pose()

    # Capture based on source type
    if isinstance(mgr, _WebcamManager):
        frame = mgr.capture(resolution=resolution)
        if frame is None:
            return None

        pt_degs = get_pan_tilt_degs() if source == "pan_tilt" else None

        result = CaptureResult(
            image=frame,
            source=source,
            pose=pose,
            pan_tilt_degs=pt_degs,
            meta=meta,
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
            meta=meta,
        )
    else:
        return None

    # Auto-save and/or view
    if view or save:
        result.save(view=view, meta_keys=meta_keys)

    return result


def crop(
    image_or_result: Union[np.ndarray, CaptureResult],
    box_2d: List[float],
) -> Union[np.ndarray, CaptureResult]:
    """
    Crop a region from an image using normalized 0-1000 coordinates.

    Convenience wrapper that accepts either a raw ndarray or a CaptureResult.

    Args:
        image_or_result: The image to crop from. Either an np.ndarray or
            a CaptureResult object.
        box_2d: Bounding box as [y_min, x_min, y_max, x_max] in 0-1000
            normalized coordinates.

    Returns:
        If input is CaptureResult -> returns a new CaptureResult.
        If input is np.ndarray -> returns a cropped np.ndarray (BGR uint8).
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


def _get_bridge():
    global _bridge
    if _bridge is None and _HAS_ROS:
        from cv_bridge import CvBridge
        _bridge = CvBridge()
    return _bridge

def _get_debug_pub(source: str):
    """Lazy-init a publisher for a specific debug source."""
    global _debug_pubs
    if source not in _debug_pubs and _HAS_ROS:
        topic = f"/logos/debug_vision/{source}"
        from sensor_msgs.msg import Image as ROSImage
        _debug_pubs[source] = rospy.Publisher(topic, ROSImage, queue_size=2, latch=True)
    return _debug_pubs.get(source)


_DEBUG_BOX_COLORS: Tuple[Tuple[int, int, int], ...] = (
    (0, 255, 255),    # yellow
    (255, 0, 255),    # magenta
    (255, 255, 0),    # cyan
    (0, 165, 255),    # orange
    (255, 128, 0),    # blue-cyan
    (128, 0, 255),    # violet
    (0, 255, 0),      # green
    (255, 0, 0),      # blue
)


def _is_detection_dict(value: Any) -> bool:
    """Return True if a dict looks like one of my visual detection records."""
    return isinstance(value, dict) and (
        "box_2d" in value
        or "bbox" in value
        or "bounding_box" in value
        or "center_2d" in value
        or "landmarks" in value
    )


def _coerce_detection_list(value: Any) -> List[Dict[str, Any]]:
    """
    Normalize several detection container shapes into a flat list of dicts.

    This accepts the normal model output list, a single detection dict, the
    `(detections, CaptureResult)` tuple returned by models when passed a
    CaptureResult, and nested metadata forms like `{"detections": [...]}`.
    """
    if value is None:
        return []

    if _is_detection_dict(value):
        return [value]

    if isinstance(value, tuple):
        if len(value) == 2 and isinstance(value[0], (list, tuple, dict)):
            return _coerce_detection_list(value[0])
        value = list(value)

    if isinstance(value, list):
        detections: List[Dict[str, Any]] = []
        for item in value:
            if _is_detection_dict(item):
                detections.append(item)
            elif isinstance(item, (list, tuple, dict)):
                detections.extend(_coerce_detection_list(item))
        return detections

    if isinstance(value, dict):
        for key in (
            "detections",
            "detection_results",
            "results",
            "objects",
            "items",
            "hands",
            "boxes",
        ):
            if key in value:
                detections = _coerce_detection_list(value[key])
                if detections:
                    return detections

        detections = []
        for item in value.values():
            detections.extend(_coerce_detection_list(item))
        if detections:
            return detections

    return []


def _source_from_meta_key(key: str) -> Optional[str]:
    """Infer a readable debug source from a metadata key."""
    lowered = key.lower()
    for prefix in ("det_", "detections_", "detection_", "vision_"):
        if lowered.startswith(prefix) and len(lowered) > len(prefix):
            return lowered[len(prefix):]
    if lowered in ("detections", "detection_results"):
        return "detections"
    return None


def _source_from_detections(detections: List[Dict[str, Any]]) -> Optional[str]:
    """Infer a source name when detections carry a consistent source field."""
    sources = []
    for det in detections:
        source = det.get("source")
        if source:
            sources.append(str(source))

    unique_sources = sorted(set(sources))
    if len(unique_sources) == 1:
        return unique_sources[0]
    if len(unique_sources) > 1:
        return "mixed"
    return None


def _find_meta_detections(meta: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Find detection-shaped metadata even when the key names vary.

    I prefer explicit detection-ish keys, but I also inspect nested dict values
    so older or ad-hoc metadata can still be visualized.
    """
    if not isinstance(meta, dict):
        return [], None

    detections: List[Dict[str, Any]] = []
    matched_sources: List[str] = []
    detection_tokens = ("det", "detect", "yolo", "hand", "object", "box", "vision")

    for key, value in meta.items():
        key_text = str(key)
        lowered = key_text.lower()
        key_looks_relevant = (
            lowered in ("detections", "detection_results", "objects", "boxes", "hands")
            or any(token in lowered for token in detection_tokens)
        )

        found = _coerce_detection_list(value)
        if found and key_looks_relevant:
            detections.extend(found)
            inferred = _source_from_meta_key(key_text)
            if inferred:
                matched_sources.append(inferred)

    if not detections:
        return [], None

    source = None
    unique_meta_sources = sorted(set(matched_sources))
    if len(unique_meta_sources) == 1:
        source = unique_meta_sources[0]
    elif len(unique_meta_sources) > 1:
        source = "mixed"

    return detections, source or _source_from_detections(detections)


def _sanitize_debug_source(source: Optional[str]) -> str:
    """Keep debug source names ROS-topic friendly."""
    if not source:
        return "general"

    cleaned = []
    for char in str(source).strip():
        if char.isalnum() or char in ("_", "-"):
            cleaned.append(char)
        elif char.isspace() or char in ("/", ".", ":"):
            cleaned.append("_")

    text = "".join(cleaned).strip("_")
    return text or "general"


def _debug_meta_key(source: str, detections: List[Dict[str, Any]]) -> str:
    """Choose where explicit debug detections should live on a CaptureResult."""
    det_source = _source_from_detections(detections)
    base = det_source or source or "debug"
    return "det_" + _sanitize_debug_source(base)


@api_call(default_verbosity=Verbosity.SILENT)
def publish_debug(
    image: Union[np.ndarray, CaptureResult],
    detections: Optional[Union[List[Dict[str, Any]], Dict[str, Any], Tuple[Any, ...]]] = None,
    source: Optional[str] = None,
) -> None:
    """
    Annotate an image with detection boxes and labels, then publish to ROS.
    
    Topic: /logos/debug_vision/{source}

    Args:
        image: The base BGR image, or a CaptureResult with `.image` and `.meta`.
        detections: Optional Logos-format detection data. Can be a list, a single
            detection dict, a nested dict containing detections, or the
            `(detections, CaptureResult)` tuple returned by logos.models.
        source: Optional string used to name the ROS topic. If omitted for a
            CaptureResult, it will be inferred from detection metadata.

    Note to self:
        This is how I show Mark what I'm seeing and thinking. I would use
        this to request a sanity check from human eyes, or if Mark specifically
        asks me to.
    """
    capture_result = image if isinstance(image, CaptureResult) else None
    base_image = capture_result.image if capture_result is not None else image
    normalized_detections = _coerce_detection_list(detections)
    inferred_source = None

    if capture_result is not None:
        if normalized_detections:
            meta_key = _debug_meta_key(source or "debug", normalized_detections)
            capture_result.add_meta(**{meta_key: normalized_detections})
        else:
            normalized_detections, inferred_source = _find_meta_detections(capture_result.meta)

    if inferred_source is None:
        inferred_source = _source_from_detections(normalized_detections)

    debug_source = _sanitize_debug_source(source or inferred_source or "general")

    if not _HAS_ROS:
        return
    
    bridge = _get_bridge()
    pub = _get_debug_pub(debug_source)
    if not bridge or not pub: return

    # Work on a copy so we don't modify the original image object
    canvas = base_image.copy()
    h, w = canvas.shape[:2]

    if normalized_detections:
        for i, det in enumerate(normalized_detections):
            box = det.get("box_2d")
            if not box or len(box) != 4: continue
            
            # Map 0-1000 to pixel coordinates
            y1, x1, y2, x2 = [
                int(box[0] * h / 1000), int(box[1] * w / 1000),
                int(box[2] * h / 1000), int(box[3] * w / 1000)
            ]

            color = _DEBUG_BOX_COLORS[i % len(_DEBUG_BOX_COLORS)]

            # Draw Box
            cv2.rectangle(canvas, (x1, y1), (x2, y2), color, 2)

            # Draw Label & Confidence
            label = det.get("label") or det.get("gesture") or det.get("handedness") or "unknown"
            conf = det.get("confidence")
            text = f"{label} {conf}" if conf else label
            
            # Simple text background for readability
            cv2.putText(canvas, text, (x1, y1 - 10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA)

    # Publish to ROS
    try:
        msg = bridge.cv2_to_imgmsg(canvas, encoding="bgr8")
        msg.header.stamp = rospy.Time.now()
        pub.publish(msg)
    except Exception as e:
        print(f"vision: Failed to publish debug image: {e}")


# ============================================================================
# HUD System
# ============================================================================
#
# The HUD (Heads-Up Display) system for overlaying text and graphical elements
# onto rendered images. Originally from map3d.py, now extracted here so it can
# be reused for real camera image overlays too.

from dataclasses import dataclass

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
HUD_FONT_MONO = 7           # cv2.FONT_HERSHEY_SCRIPT_SIMPLEX (not actually mono)
# For actual monospace, FONT_HERSHEY_PLAIN (1) is closest in OpenCV.


@dataclass
class HudElement:
    """
    A single text element to overlay on a rendered image.

    Positioning uses named anchors (see HUD_ANCHORS). Multiple elements
    at the same anchor are stacked vertically, sorted by priority (lower
    values render closer to the anchor edge, i.e. top for top_*, bottom
    for bottom_*).

    Colors are BGR uint8 tuples for direct OpenCV compatibility.

    Attributes:
        text: The text to display
        anchor: Position anchor (one of HUD_ANCHORS)
        color: Text color as BGR tuple (0-255)
        bg_color: Background color as BGR tuple, or None for no background
        bg_alpha: Background transparency (0.0 = transparent, 1.0 = opaque)
        font_scale: OpenCV font scale factor
        thickness: Text stroke thickness in pixels
        font: OpenCV font constant (e.g., HUD_FONT_SIMPLEX)
        margin_px: Padding from image edge and between stacked elements
        priority: Lower values render closer to anchor edge
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


def overlay_hud(
    image: np.ndarray,
    elements: List[HudElement],
) -> np.ndarray:
    """
    Render HUD elements onto an image.

    This composites text overlays at the specified anchor positions.
    Elements at the same anchor are stacked vertically by priority.

    Args:
        image: BGR uint8 numpy array (modified in-place)
        elements: List of HudElement objects to render

    Returns:
        The modified image (same reference as input)

    Note to self:
        This is how I annotate my visual field with contextual information.
        I can add warnings, status indicators, coordinates, labels, or any
        text I need to see while reasoning about an image.
    """
    if not elements:
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

    # Render each group
    for anchor, elems in groups.items():
        is_top = anchor.startswith("top")
        is_right = anchor.endswith("right")
        is_center = anchor.endswith("center")

        # Pre-compute text sizes for each element
        line_infos = []
        for el in elems:
            (tw, th), baseline = cv2.getTextSize(
                el.text, el.font, el.font_scale, el.thickness
            )
            line_infos.append(((tw, th), baseline, el))

        # Compute starting Y position
        margin = elems[0].margin_px if elems else 8
        if is_top:
            y_cursor = margin
        else:
            # For bottom anchors, start from bottom and work up
            total_h = sum(ts[1] + bl + margin for (ts, bl, _) in line_infos)
            y_cursor = h_img - total_h - margin

        # Render each element
        for (tw, th), baseline, el in line_infos:
            pad = el.margin_px
            line_h = th + baseline

            # Compute X position based on anchor
            if is_center:
                x = (w_img - tw) // 2
            elif is_right:
                x = w_img - tw - pad
            else:
                x = pad

            text_y = y_cursor + th

            # Draw background rectangle if specified
            if el.bg_color is not None:
                x1 = max(x - pad, 0)
                y1 = max(y_cursor - pad // 2, 0)
                x2 = min(x + tw + pad, w_img)
                y2 = min(text_y + baseline + pad // 2, h_img)

                if el.bg_alpha >= 1.0:
                    # Fully opaque background
                    cv2.rectangle(
                        image, (x1, y1), (x2, y2),
                        el.bg_color, cv2.FILLED,
                    )
                elif el.bg_alpha > 0.0:
                    # Semi-transparent background via alpha blending
                    roi = image[y1:y2, x1:x2].copy()
                    overlay = np.full_like(roi, el.bg_color, dtype=np.uint8)
                    blended = cv2.addWeighted(
                        overlay, el.bg_alpha,
                        roi, 1.0 - el.bg_alpha,
                        0,
                    )
                    image[y1:y2, x1:x2] = blended

            # Draw text
            cv2.putText(
                image, el.text, (x, text_y),
                el.font, el.font_scale, el.color, el.thickness,
                cv2.LINE_AA,
            )

            y_cursor += line_h + pad

    return image


def make_quad_composite(
    items: List[Union[np.ndarray, CaptureResult]],
    labels: Optional[List[str]] = None,
    meta_keys: Optional[List[str]] = None,
    target_res: Tuple[int, int] = (960, 1280)
) -> CaptureResult:
    """
    Stitches up to 4 images into a 2x2 grid (Quad View) with metadata overlays.

    Layout:
        0 | 1
        --+--
        2 | 3

    Args:
        items: List of 1-4 images (numpy arrays) or CaptureResult objects.
        labels: Optional list of custom base labels for each quadrant.
                If None, defaults to the source name (e.g., "pan_tilt").
        meta_keys: Optional list of wildcard patterns (e.g., ["pan_tilt*", "pose"])
                   to select metadata fields to display below the label.
        target_res: (Height, Width) of the final composite image.
                    Default (960, 1280) -> quadrants are 480x640.

    Returns:
        A new CaptureResult containing the composite image.
    """
    total_h, total_w = target_res
    quad_h, quad_w = total_h // 2, total_w // 2
    
    # Create black canvas
    canvas = np.zeros((total_h, total_w, 3), dtype=np.uint8)
    
    # Quadrant offsets: (y, x)
    offsets = [
        (0, 0),           # 0: Top-Left
        (0, quad_w),      # 1: Top-Right
        (quad_h, 0),      # 2: Bottom-Left
        (quad_h, quad_w)  # 3: Bottom-Right
    ]

    for i in range(min(len(items), 4)):
        item = items[i]
        
        # --- Prepare Image & Text ---
        hud_lines = []
        
        if isinstance(item, CaptureResult):
            img = item.image
            
            # 1. Base Label
            if labels and i < len(labels) and labels[i]:
                base_label = labels[i]
            else:
                base_label = item.source
            hud_lines.append(base_label)
            
            # 2. Metadata Filtering
            if meta_keys:
                # Merge system props with custom meta for filtering
                # This ensures we catch 'pan_tilt_degs' even if not saved to disk yet
                lookup = item.meta.copy()
                if item.pan_tilt_degs:
                    lookup['pan_tilt'] = item.pan_tilt_degs
                if item.pose:
                    lookup['pose'] = item.pose
                
                for key, val in lookup.items():
                    for pattern in meta_keys:
                        if fnmatch.fnmatch(key, pattern):
                            # Format values compactly
                            if isinstance(val, float):
                                val_str = f"{val:.1f}"
                            elif isinstance(val, (list, tuple)) and len(val) == 2 and isinstance(val[0], float):
                                # Compact formatting for [pan, tilt]
                                val_str = f"[{val[0]:.0f}, {val[1]:.0f}]"
                            elif isinstance(val, dict) and 'x' in val:
                                # Compact pose
                                val_str = f"x:{val['x']:.1f} y:{val['y']:.1f}"
                            else:
                                val_str = str(val)
                            
                            hud_lines.append(f"{key}: {val_str}")
                            break # Match found for this key, move to next
        else:
            # Plain numpy array
            img = item
            text = labels[i] if (labels and i < len(labels)) else f"Cam {i}"
            hud_lines.append(text)

        # --- Resize & Overlay ---
        # Resize to fit quadrant
        if img.shape[:2] != (quad_h, quad_w):
            img = cv2.resize(img, (quad_w, quad_h), interpolation=cv2.INTER_AREA)

        # Apply HUD elements stacked vertically
        hud_elements = []
        for j, line in enumerate(hud_lines):
            hud_elements.append(HudElement(
                text=line,
                anchor="top_left",
                priority=j,
                font_scale=0.4,
                thickness=1,
                bg_color=(0, 0, 0),
                bg_alpha=0.6,
                margin_px=5
            ))
            
        overlay_hud(img, hud_elements)

        # --- Paste into Canvas ---
        y_off, x_off = offsets[i]
        canvas[y_off:y_off+quad_h, x_off:x_off+quad_w] = img

    # --- Draw Dividers ---
    # To separate quadrants
    cv2.line(canvas, (0, quad_h), (total_w, quad_h), (0, 0, 0), 2)
    cv2.line(canvas, (quad_w, 0), (quad_w, total_h), (0, 0, 0), 2)

    return CaptureResult(
        image=canvas,
        source="composite",
        meta={"composition": "quad_view", "count": len(items)}
    )

__all__ = [
    "capture", "crop", "publish_debug",
    "CaptureResult", "FOV", "DEFAULT_RESOLUTION", "SOURCES",
    "HudElement", "HUD_ANCHORS",
    "HUD_FONT_SIMPLEX", "HUD_FONT_PLAIN", "HUD_FONT_DUPLEX",
    "HUD_FONT_SMALL", "HUD_FONT_MONO",
    "overlay_hud",
    "make_quad_composite"
]
