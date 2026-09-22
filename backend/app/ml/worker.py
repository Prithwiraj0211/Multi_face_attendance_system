import time
import threading
import logging
import asyncio
from backend.app.ml.camera import camera_manager
from backend.app.ml.face_engine import face_engine
from backend.app.ml.attendance_engine import attendance_engine

logger = logging.getLogger("attendance.vision_worker")

class VisionWorker:
    def __init__(self):
        self.is_running = False
        self.thread = None
        self.fps = 0.0
        self.last_frame_time = time.time()
        self.latest_detections = []
        self._lock = threading.Lock()
        self.websocket_broadcast_callback = None

    def register_broadcast_callback(self, callback):
        """Callback to dispatch WebSocket alerts across clients."""
        self.websocket_broadcast_callback = callback

    def start(self):
        with self._lock:
            if self.is_running:
                return
            self.is_running = True
            camera_manager.start()
            self.thread = threading.Thread(target=self._run_loop, daemon=True)
            self.thread.start()
            logger.info("Vision processing worker started.")

    def stop(self):
        with self._lock:
            self.is_running = False
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=2.0)
            camera_manager.stop()
            logger.info("Vision processing worker stopped.")

    def _run_loop(self):
        frame_count = 0
        fps_timer = time.time()

        while self.is_running:
            try:
                start_time = time.time()
                raw_frame = camera_manager.get_latest_frame()

                if raw_frame is None or not camera_manager.camera_connected:
                    annotated = camera_manager.get_latest_frame()
                    camera_manager.set_annotated_frame(annotated)
                    time.sleep(0.05)
                    continue

                # Run Multi-Face detection and recognition
                detections = face_engine.detect_and_recognize_all(raw_frame)
                self.latest_detections = detections

                # Process attendance punch debounce & state machine
                new_punches = attendance_engine.process_detections(detections, raw_frame)

                # Trigger real-time notifications if new punch occurred
                if new_punches and self.websocket_broadcast_callback:
                    for punch in new_punches:
                        try:
                            self.websocket_broadcast_callback(punch)
                        except Exception as e:
                            logger.error(f"Error calling websocket broadcast: {e}")

                # Calculate FPS
                frame_count += 1
                if time.time() - fps_timer >= 1.0:
                    self.fps = frame_count / (time.time() - fps_timer)
                    frame_count = 0
                    fps_timer = time.time()

                # Render HUD overlays
                annotated_frame = face_engine.draw_hud(raw_frame, detections, fps=self.fps)
                camera_manager.set_annotated_frame(annotated_frame)

                # Slight yield to avoid pegging CPU at 100%
                elapsed = time.time() - start_time
                if elapsed < 0.02: # Target ~30-40 FPS
                    time.sleep(0.02 - elapsed)

            except Exception as e:
                logger.error(f"Vision loop error (recovering): {e}")
                time.sleep(0.05)

vision_worker = VisionWorker()
