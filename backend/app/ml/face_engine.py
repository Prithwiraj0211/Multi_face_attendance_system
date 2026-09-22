import time
import logging
import threading
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
import cv2
import numpy as np
from backend.app.core.config import settings
from backend.app.ml.anti_spoof import anti_spoof_detector

logger = logging.getLogger("attendance.face_engine")

@dataclass
class DetectedFace:
    bbox: Tuple[int, int, int, int] # x, y, w, h
    landmarks: np.ndarray          # 5 landmarks
    confidence: float              # detection score
    is_real: bool                  # liveness
    liveness_score: float
    feature: Optional[np.ndarray] = None
    employee_id: Optional[int] = None
    employee_name: Optional[str] = None
    employee_code: Optional[str] = None
    department: Optional[str] = None
    similarity: float = 0.0
    status: str = "UNKNOWN"        # VERIFIED, UNKNOWN, SPOOF

class FaceEngine:
    def __init__(self):
        self.yunet_path = str(settings.YUNET_MODEL_PATH)
        self.sface_path = str(settings.SFACE_MODEL_PATH)
        
        self._lock = threading.Lock()
        self.detector = None
        self.recognizer = None
        self.match_threshold = settings.FACE_MATCH_THRESHOLD
        self.conf_threshold = settings.FACE_DETECTOR_CONF_THRESHOLD
        
        # In-memory vector cache for microsecond lookups
        # Format: {emp_id: {"name": str, "code": str, "dept": str, "feature": np.ndarray}}
        self.known_faces: Dict[int, Dict[str, Any]] = {}
        
        self._init_models()
        
    def _init_models(self):
        """Initialize YuNet and SFace OpenCV DNN models."""
        try:
            self.detector = cv2.FaceDetectorYN.create(
                model=self.yunet_path,
                config="",
                input_size=(settings.FRAME_WIDTH, settings.FRAME_HEIGHT),
                score_threshold=self.conf_threshold,
                nms_threshold=0.3,
                top_k=5000
            )
            self.recognizer = cv2.FaceRecognizerSF.create(
                model=self.sface_path,
                config=""
            )
            logger.info("YuNet Multi-Face Detector and SFace Recognizer initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize face models: {e}")
            raise e

    def reload_embeddings_from_db(self, db_session):
        """Load all active employees' face embeddings from database into RAM cache."""
        from backend.app.db.models import Employee, FaceEmbedding
        
        updated_cache = {}
        try:
            employees = (
                db_session.query(Employee)
                .filter(Employee.is_active == True)
                .all()
            )
            for emp in employees:
                if emp.embeddings:
                    # Cache all enrolled embeddings for this employee to maximize recognition accuracy across angles/lighting
                    features_list = [emb.get_embedding().reshape(1, 128) for emb in emp.embeddings]
                    updated_cache[emp.id] = {
                        "name": emp.full_name,
                        "code": emp.employee_code,
                        "dept": emp.department,
                        "features": features_list
                    }
            self.known_faces = updated_cache
            logger.info(f"Face Engine: Cached embeddings for {len(self.known_faces)} employees.")
        except Exception as e:
            logger.error(f"Error reloading embeddings from database: {e}")

    def detect_and_recognize_all(self, frame: np.ndarray) -> List[DetectedFace]:
        """
        Processes a single frame for MULTI-FACE detection and recognition.
        Returns a list of DetectedFace objects for all people detected simultaneously.
        """
        if frame is None or frame.size == 0 or self.detector is None or self.recognizer is None:
            return []

        with self._lock:
            h, w = frame.shape[:2]
            self.detector.setInputSize((w, h))

            retval, faces = self.detector.detect(frame)
            if faces is None or len(faces) == 0:
                return []

            results: List[DetectedFace] = []

            for face in faces:
                # Face array: [x, y, w, h, x_re, y_re, x_le, y_le, x_nt, y_nt, x_rcm, y_rcm, x_lcm, y_lcm, score]
                x, y, fw, fh = map(int, face[0:4])
                score = float(face[-1])
                landmarks = face[4:14].reshape((5, 2))

                # Boundary clipping
                x = max(0, min(x, w - 1))
                y = max(0, min(y, h - 1))
                fw = max(1, min(fw, w - x))
                fh = max(1, min(fh, h - y))

                # Discard low-resolution / tiny faces to avoid false positives
                if fw < 45 or fh < 45:
                    continue

                # Crop face for liveness/anti-spoof test
                face_crop = frame[y:y+fh, x:x+fw]
                liveness_info = anti_spoof_detector.check_liveness(face_crop)
                is_real = liveness_info["is_real"]

                # Align and extract 128D feature
                aligned_face = self.recognizer.alignCrop(frame, face)
                feature = self.recognizer.feature(aligned_face) # Shape (1, 128)

                # Match against known employees (evaluates all enrolled reference embeddings)
                best_match_id = None
                best_sim = -1.0
                best_meta = None

                for emp_id, data in self.known_faces.items():
                    emp_best_sim = -1.0
                    for known_feat in data.get("features", []):
                        sim = self.recognizer.match(feature, known_feat, cv2.FaceRecognizerSF_FR_COSINE)
                        if sim > emp_best_sim:
                            emp_best_sim = sim
                    if emp_best_sim > best_sim:
                        best_sim = emp_best_sim
                        best_match_id = emp_id
                        best_meta = data

                if not is_real:
                    status = "SPOOF_SUSPECT"
                    emp_name = "Fake / Spoof Alert"
                    emp_code = "ALERT"
                    dept = "Security"
                elif best_sim >= self.match_threshold and best_meta is not None:
                    status = "VERIFIED"
                    emp_name = best_meta["name"]
                    emp_code = best_meta["code"]
                    dept = best_meta["dept"]
                else:
                    status = "UNKNOWN"
                    emp_name = "Unregistered Person"
                    emp_code = "UNKNOWN"
                    dept = "Visitor"

                detected = DetectedFace(
                    bbox=(x, y, fw, fh),
                    landmarks=landmarks,
                    confidence=round(score, 2),
                    is_real=is_real,
                    liveness_score=liveness_info["liveness_score"],
                    feature=feature,
                    employee_id=best_match_id if status == "VERIFIED" else None,
                    employee_name=emp_name,
                    employee_code=emp_code,
                    department=dept,
                    similarity=round(float(max(0.0, best_sim)), 3),
                    status=status
                )
                results.append(detected)

            return results

    def extract_single_face_feature(self, bgr_image: np.ndarray) -> Tuple[bool, Optional[np.ndarray], str, Optional[np.ndarray]]:
        """
        Used during Employee Face Registration (1-click camera snapshot or upload).
        Ensures a clean single face is detected, extracts 128D embedding, and returns cropped portrait.
        """
        if bgr_image is None or bgr_image.size == 0:
            return False, None, "Invalid image data.", None

        with self._lock:
            h, w = bgr_image.shape[:2]
            self.detector.setInputSize((w, h))
            retval, faces = self.detector.detect(bgr_image)

            if faces is None or len(faces) == 0:
                return False, None, "No face detected. Please position face clearly in good lighting.", None

            if len(faces) > 1:
                # Pick the largest face if multiple are present in registration
                faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)

            face = faces[0]
            aligned = self.recognizer.alignCrop(bgr_image, face)
            feature = self.recognizer.feature(aligned)
            
            # Verify vector normalization
            vec = feature.flatten()
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm

            # Crop face with margin for clean portrait avatar
            x, y, fw, fh = map(int, face[0:4])
            pad_x = int(fw * 0.25)
            pad_y = int(fh * 0.35)
            x1 = max(0, x - pad_x)
            y1 = max(0, y - pad_y)
            x2 = min(w, x + fw + pad_x)
            y2 = min(h, y + fh + int(pad_y * 0.8))
            face_crop = bgr_image[y1:y2, x1:x2]

            return True, vec, "Face enrolled successfully.", face_crop

    def draw_hud(self, frame: np.ndarray, detections: List[DetectedFace], fps: float = 0.0) -> np.ndarray:
        """
        Render dynamic glassmorphic cyber HUD over video frame.
        - Corner brackets
        - Glowing labels with name, code, dept, confidence
        - Live FPS and Multi-face count badge
        """
        annotated = frame.copy()
        h, w = annotated.shape[:2]

        # Top Banner Overlay
        cv2.rectangle(annotated, (0, 0), (w, 36), (15, 12, 10), -1)
        cv2.putText(
            annotated,
            f"AI MULTI-FACE RECOGNITION | FPS: {fps:.1f} | DETECTED: {len(detections)}",
            (15, 24),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 240, 255),
            1,
            cv2.LINE_AA
        )

        for det in detections:
            x, y, fw, fh = det.bbox

            if det.status == "VERIFIED":
                # Emerald Cyan / Green
                color = (70, 230, 90)
                tag_bg = (30, 80, 40)
            elif det.status == "SPOOF_SUSPECT":
                # Orange / Warning
                color = (0, 140, 255)
                tag_bg = (20, 40, 90)
            else:
                # Crimson / Magenta
                color = (80, 80, 240)
                tag_bg = (30, 20, 80)

            # Draw Cyber Corner Brackets
            corner_len = min(22, fw // 4, fh // 4)
            thickness = 2
            # Top-left
            cv2.line(annotated, (x, y), (x + corner_len, y), color, thickness)
            cv2.line(annotated, (x, y), (x, y + corner_len), color, thickness)
            # Top-right
            cv2.line(annotated, (x + fw, y), (x + fw - corner_len, y), color, thickness)
            cv2.line(annotated, (x + fw, y), (x + fw, y + corner_len), color, thickness)
            # Bottom-left
            cv2.line(annotated, (x, y + fh), (x + corner_len, y + fh), color, thickness)
            cv2.line(annotated, (x, y + fh), (x, y + fh - corner_len), color, thickness)
            # Bottom-right
            cv2.line(annotated, (x + fw, y + fh), (x + fw - corner_len, y + fh), color, thickness)
            cv2.line(annotated, (x + fw, y + fh), (x + fw, y + fh - corner_len), color, thickness)

            # Draw bounding box thin outline
            cv2.rectangle(annotated, (x, y), (x + fw, y + fh), color, 1)

            # Header label pill
            label = f"{det.employee_name}"
            sublabel = f"{det.department} | {int(det.similarity * 100)}%" if det.status == "VERIFIED" else det.status

            pill_y1 = max(0, y - 38)
            pill_y2 = y
            pill_w = max(140, int(len(label) * 9.5))

            # Dark translucent backing
            sub_rect = annotated[pill_y1:pill_y2, x:min(w, x + pill_w)]
            if sub_rect.shape[0] > 0 and sub_rect.shape[1] > 0:
                overlay = np.full(sub_rect.shape, tag_bg, dtype=np.uint8)
                cv2.addWeighted(overlay, 0.85, sub_rect, 0.15, 0, sub_rect)

            cv2.putText(
                annotated,
                label,
                (x + 6, max(14, y - 20)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                (255, 255, 255),
                1,
                cv2.LINE_AA
            )
            cv2.putText(
                annotated,
                sublabel,
                (x + 6, max(28, y - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                color,
                1,
                cv2.LINE_AA
            )

        return annotated

# Global face engine instance
face_engine = FaceEngine()
