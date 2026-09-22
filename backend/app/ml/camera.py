import cv2
import threading
import time
import logging
import numpy as np
from backend.app.core.config import settings

logger = logging.getLogger("attendance.camera")

class CameraManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance
            
    def __init__(self):
        if self._initialized:
            return
            
        self.camera_index = settings.CAMERA_INDEX
        self.frame_width = settings.FRAME_WIDTH
        self.frame_height = settings.FRAME_HEIGHT
        self.target_fps = settings.CAMERA_FPS
        
        self.cap = None
        self.latest_raw_frame = None
        self.latest_annotated_frame = None
        self.is_running = False
        self.thread = None
        self.frame_lock = threading.Lock()
        self.camera_connected = False
        
        self._initialized = True
        
    def start(self):
        """Start background camera thread."""
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            self.thread = threading.Thread(target=self._capture_loop, daemon=True)
            self.thread.start()
            logger.info("Camera background thread started.")
            
    def stop(self):
        """Stop background camera thread and release hardware."""
        with self._lock:
            self.is_running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2.0)
            if self.cap:
                self.cap.release()
                self.cap = None
            self.camera_connected = False
            logger.info("Camera released.")
            
    def _open_capture(self):
        """Try opening camera with DirectShow first (best for Windows), then standard fallback."""
        try:
            # Try DSHOW on Windows
            cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                cap = cv2.VideoCapture(self.camera_index)
                
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
                cap.set(cv2.CAP_PROP_FPS, self.target_fps)
                return cap
        except Exception as e:
            logger.error(f"Error opening camera index {self.camera_index}: {e}")
        return None
        
    def _capture_loop(self):
        """Continuous background capture loop."""
        self.cap = self._open_capture()
        self.camera_connected = self.cap is not None and self.cap.isOpened()
        
        frame_interval = 1.0 / self.target_fps
        last_reconnect_time = time.time()
        
        while self.is_running:
            start_time = time.time()
            
            if self.cap is None or not self.cap.isOpened():
                self.camera_connected = False
                # Reconnect attempt every 3 seconds
                if time.time() - last_reconnect_time > 3.0:
                    last_reconnect_time = time.time()
                    self.cap = self._open_capture()
                    self.camera_connected = self.cap is not None and self.cap.isOpened()
                    
                # Generate synthetic standby frame if camera is unavailable
                frame = self._create_standby_frame()
                with self.frame_lock:
                    self.latest_raw_frame = frame
                time.sleep(0.05)
                continue
                
            ret, frame = self.cap.read()
            if not ret or frame is None:
                self.camera_connected = False
                time.sleep(0.03)
                continue
                
            self.camera_connected = True
            with self.frame_lock:
                self.latest_raw_frame = frame
                
            # Maintain target FPS
            elapsed = time.time() - start_time
            sleep_time = max(0.0, frame_interval - elapsed)
            if sleep_time > 0:
                time.sleep(sleep_time)
                
    def get_latest_frame(self):
        """Retrieve copy of the latest raw camera frame."""
        with self.frame_lock:
            if self.latest_raw_frame is not None:
                return self.latest_raw_frame.copy()
            return self._create_standby_frame()
            
    def set_annotated_frame(self, frame):
        """Store the latest annotated frame (with HUD and bounding boxes)."""
        with self.frame_lock:
            self.latest_annotated_frame = frame
            
    def get_annotated_frame(self):
        """Retrieve copy of the latest annotated frame."""
        with self.frame_lock:
            if self.latest_annotated_frame is not None:
                return self.latest_annotated_frame.copy()
            if self.latest_raw_frame is not None:
                return self.latest_raw_frame.copy()
            return self._create_standby_frame()
            
    def _create_standby_frame(self):
        """Generate sleek standby frame when physical camera is offline."""
        img = np.zeros((self.frame_height, self.frame_width, 3), dtype=np.uint8)
        # Deep blue-gray gradient
        img[:] = (20, 15, 10)
        
        # Center text
        cv2.putText(
            img, "CAMERA INITIALIZING / CONNECTING...",
            (int(self.frame_width * 0.15), int(self.frame_height * 0.48)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.65, (100, 200, 255), 2, cv2.LINE_AA
        )
        cv2.putText(
            img, "Ensure Webcam is enabled and not in use by another app",
            (int(self.frame_width * 0.12), int(self.frame_height * 0.56)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA
        )
        return img

# Global camera manager instance
camera_manager = CameraManager()
