# Logos/src/logos/vision/cameras.py

"""
This module manages the camera hardware and ROS subscriptions.
It implements the "Hybrid Lazy" logic to save resources while keeping
me ready for action.
"""

import threading
import time
import cv2
import numpy as np
import rospy
import message_filters
from sensor_msgs.msg import Image
from cv_bridge import CvBridge
from typing import Optional, Tuple, Dict
from .core import (
    CameraState, CAM_PAN_TILT, CAM_TOP_DOWN, CAM_ASTRA
)

# Constants
WARMUP_FRAMES_USB = 5
WARMUP_FRAMES_ASTRA = 15  # RGBD sensors take a bit longer to stabilize auto-exposure
COOLDOWN_SECONDS = 90.0   # How long to stay HOT after last use

class CameraInterface:
    """Abstract base for my eyes."""
    def __init__(self, name: str):
        self.name = name
        self.state = CameraState.COLD
        self.last_access_time = 0.0
        self.lock = threading.Lock()
        
    def get_latest_frame(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Returns (rgb_image, depth_image). Depth may be None."""
        raise NotImplementedError

    def _update_access_time(self):
        self.last_access_time = time.time()

    def check_cooldown(self):
        """Called periodically to check if we should shut down."""
        if self.state == CameraState.HOT:
            if (time.time() - self.last_access_time) > COOLDOWN_SECONDS:
                self.shutdown()

    def shutdown(self):
        raise NotImplementedError


class USBCamera(CameraInterface):
    """
    Manages a local USB webcam (Pan/Tilt or Top-Down).
    Acts as a driver + ROS publisher.
    """
    def __init__(self, name: str, device_path: str, topic_name: str, flip: bool = False):
        super().__init__(name)
        self.device_path = device_path
        self.topic_name = topic_name
        self.flip = flip
        
        self.cap: Optional[cv2.VideoCapture] = None
        self.bridge = CvBridge()
        self.pub = rospy.Publisher(topic_name, Image, queue_size=2)
        
        self.latest_rgb: Optional[np.ndarray] = None
        self.running = False
        self.worker_thread: Optional[threading.Thread] = None

    def _start(self):
        """Internal start sequence."""
        if self.running: 
            return
            
        rospy.loginfo(f"[{self.name}] Starting camera at {self.device_path}...")
        self.cap = cv2.VideoCapture(self.device_path)
        
        # Set preference for 640x480 for speed/compat unless we change it later
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        
        self.running = True
        self.state = CameraState.WARMING
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.worker_thread.start()

    def _worker_loop(self):
        """
        The heartbeat of the camera.
        Reads frames, handles warmup, and publishes if necessary.
        """
        frame_count = 0
        
        while self.running and self.cap.isOpened():
            ret, frame = self.cap.read()
            if not ret:
                rospy.logwarn(f"[{self.name}] Failed to read frame.")
                time.sleep(0.1)
                continue

            # Flip if needed (Pan/Tilt is upside down)
            if self.flip:
                frame = cv2.flip(frame, -1) # -1 is both axes

            # State Logic
            if self.state == CameraState.WARMING:
                frame_count += 1
                if frame_count >= WARMUP_FRAMES_USB:
                    self.state = CameraState.HOT
                    rospy.loginfo(f"[{self.name}] Warmup complete. Camera is HOT.")
            
            # Update storage
            with self.lock:
                self.latest_rgb = frame

            # Hybrid Lazy Publishing:
            # Only publish to ROS if someone (like Rviz) is listening.
            if self.pub.get_num_connections() > 0:
                try:
                    msg = self.bridge.cv2_to_imgmsg(frame, "bgr8")
                    msg.header.stamp = rospy.Time.now()
                    msg.header.frame_id = f"{self.name}_optical_frame"
                    self.pub.publish(msg)
                    # Reset idle timer if external subscribers are active
                    self._update_access_time()
                except Exception as e:
                    rospy.logerr(f"[{self.name}] Publish error: {e}")

            # Sleep slightly to not hog CPU (limit to ~30fps)
            time.sleep(0.033)

        # Cleanup when loop exits
        if self.cap:
            self.cap.release()
        self.state = CameraState.COLD
        rospy.loginfo(f"[{self.name}] Camera stopped.")

    def get_latest_frame(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        self._update_access_time()
        
        # If external subscriber woke us up, we might be running but not explicitly "started" for internal use?
        # No, let's keep it simple: Ensure running.
        if not self.running:
            self._start()
            
        # Wait for warmup
        attempts = 0
        while self.state == CameraState.WARMING and attempts < 50:
            time.sleep(0.1)
            attempts += 1
            
        with self.lock:
            if self.latest_rgb is not None:
                return self.latest_rgb.copy(), None
        return None, None

    def shutdown(self):
        """Stops the thread and releases hardware."""
        self.running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=1.0)


class AstraCamera(CameraInterface):
    """
    Wraps the external ROS node for the Orbbec Astra.
    Syncs RGB and Depth.
    """
    def __init__(self):
        super().__init__(CAM_ASTRA)
        self.sub_rgb = None
        self.sub_depth = None
        self.sync = None
        self.bridge = CvBridge()
        
        self.latest_rgb = None
        self.latest_depth = None
        self.frame_counter = 0

    def _callback(self, rgb_msg, depth_msg):
        self.frame_counter += 1
        # Discard first few frames
        if self.frame_counter < WARMUP_FRAMES_ASTRA:
            self.state = CameraState.WARMING
            return
            
        self.state = CameraState.HOT
        try:
            self.latest_rgb = self.bridge.imgmsg_to_cv2(rgb_msg, "bgr8")
            # Depth is typically 16-bit mm
            self.latest_depth = self.bridge.imgmsg_to_cv2(depth_msg, "passthrough")
        except Exception as e:
            rospy.logerr(f"[Astra] Convert error: {e}")

    def _start(self):
        if self.sub_rgb:
            return
            
        rospy.loginfo("[Astra] Subscribing to RGBD topics...")
        self.frame_counter = 0
        self.state = CameraState.WARMING
        
        # Using depth_registered for alignment with RGB
        self.sub_rgb = message_filters.Subscriber('/camera/rgb/image_raw', Image)
        self.sub_depth = message_filters.Subscriber('/camera/depth_registered/image_raw', Image)
        
        # Approximate sync is usually needed over USB
        self.sync = message_filters.ApproximateTimeSynchronizer(
            [self.sub_rgb, self.sub_depth], queue_size=5, slop=0.1
        )
        self.sync.registerCallback(self._callback)

    def get_latest_frame(self) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        self._update_access_time()
        if not self.sub_rgb:
            self._start()
            
        # Wait for data
        attempts = 0
        while (self.state == CameraState.WARMING or self.latest_rgb is None) and attempts < 50:
            time.sleep(0.1)
            attempts += 1
            
        if self.latest_rgb is not None:
            return self.latest_rgb.copy(), self.latest_depth.copy()
        return None, None

    def shutdown(self):
        if self.sub_rgb:
            self.sub_rgb.unregister()
            self.sub_depth.unregister()
            self.sub_rgb = None
            self.sub_depth = None
            self.sync = None
            self.state = CameraState.COLD
            rospy.loginfo("[Astra] Unsubscribed.")


class CameraManager:
    """Singleton to hold camera instances."""
    def __init__(self):
        self.cameras: Dict[str, CameraInterface] = {}
        
        # Initialize Definitions
        self.cameras[CAM_PAN_TILT] = USBCamera(
            CAM_PAN_TILT, '/dev/pan_tilt_cam', '/pan_tilt/camera/image_raw', flip=True
        )
        self.cameras[CAM_TOP_DOWN] = USBCamera(
            CAM_TOP_DOWN, '/dev/top_down_cam', '/top_down/camera/image_raw', flip=False
        )
        self.cameras[CAM_ASTRA] = AstraCamera()

        # Start maintenance thread
        self.maint_thread = threading.Thread(target=self._maintenance_loop, daemon=True)
        self.maint_thread.start()

    def get(self, name: str) -> CameraInterface:
        if name not in self.cameras:
            raise ValueError(f"Unknown camera: {name}. Available: {list(self.cameras.keys())}")
        return self.cameras[name]

    def _maintenance_loop(self):
        """Background loop to check cooldowns."""
        while not rospy.is_shutdown():
            for cam in self.cameras.values():
                # For USB cams, check if external subs need it kept alive
                if isinstance(cam, USBCamera) and cam.pub.get_num_connections() > 0:
                    cam._update_access_time() # Keep alive
                
                cam.check_cooldown()
            time.sleep(1.0)

# Singleton Instance
_manager = CameraManager()

def get_camera(name: str) -> CameraInterface:
    return _manager.get(name)