import os
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import cv2
import numpy as np
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.datetime_utils import format_local_timestamp
from backend.app.db.database import SessionLocal
from backend.app.db.models import AttendanceLog, Employee
from backend.app.ml.face_engine import DetectedFace

logger = logging.getLogger("attendance.attendance_engine")

SNAPSHOTS_DIR = settings.DATA_DIR / "snapshots"
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

class AttendanceEngine:
    def __init__(self):
        # In-memory cooldown tracker: {emp_id: {"timestamp": float, "type": str}}
        self.cooldown_tracker: Dict[int, Dict[str, Any]] = {}
        self.cooldown_duration = settings.PUNCH_COOLDOWN_SECONDS
        
        # Operational punch mode: "AUTO" (smart toggle), "CHECK_IN" (only), "CHECK_OUT" (only)
        self.punch_mode = "AUTO"
        
        # In-memory queue of recent events for WebSocket broadcasts and UI ticker
        self.recent_events: List[dict] = []
        self.max_recent_events = 20
        self._last_prune_time = time.time()
        
    def process_detections(self, detections: List[DetectedFace], raw_frame: np.ndarray) -> List[dict]:
        """
        Evaluate all verified face detections from a frame.
        Applies cooldown debounce, determines punch type, persists to DB, and returns new event dicts.
        """
        new_punches = []
        current_time = time.time()
        
        # Periodic memory cleanup of cooldown tracker (every 10 minutes)
        if current_time - self._last_prune_time > 600:
            self._last_prune_time = current_time
            stale_keys = [
                eid for eid, data in self.cooldown_tracker.items()
                if current_time - data.get("timestamp", 0) > 86400
            ]
            for eid in stale_keys:
                self.cooldown_tracker.pop(eid, None)

        # Filter for verified employees only
        verified_faces = [d for d in detections if d.status == "VERIFIED" and d.employee_id is not None]
        if not verified_faces:
            return []

        processed_emp_ids_this_frame = set()

        db: Session = SessionLocal()
        try:
            for face in verified_faces:
                emp_id = face.employee_id
                if emp_id in processed_emp_ids_this_frame:
                    continue
                processed_emp_ids_this_frame.add(emp_id)

                # Determine punch type (CHECK_IN or CHECK_OUT) based on mode and history
                punch_type = self._determine_punch_type(db, emp_id)

                # Check cooldown
                if emp_id in self.cooldown_tracker:
                    last_punch = self.cooldown_tracker[emp_id]
                    time_diff = current_time - last_punch["timestamp"]
                    # Same punch type: debounce for full cooldown duration (5 minutes)
                    if last_punch["type"] == punch_type and time_diff < self.cooldown_duration:
                        continue
                    # Opposite punch type (e.g. Check-in -> Check-out): only require 5 seconds
                    elif last_punch["type"] != punch_type and time_diff < 5.0:
                        continue
                
                # Save snapshot
                snapshot_filename = f"punch_{emp_id}_{int(current_time)}_{uuid.uuid4().hex[:6]}.jpg"
                snapshot_rel_path = f"snapshots/{snapshot_filename}"
                snapshot_full_path = SNAPSHOTS_DIR / snapshot_filename
                
                try:
                    # Crop face with padding or save small frame thumbnail
                    x, y, fw, fh = face.bbox
                    h, w = raw_frame.shape[:2]
                    pad = 20
                    y1 = max(0, y - pad)
                    y2 = min(h, y + fh + pad)
                    x1 = max(0, x - pad)
                    x2 = min(w, x + fw + pad)
                    face_thumb = raw_frame[y1:y2, x1:x2]
                    if face_thumb.size > 0:
                        cv2.imwrite(str(snapshot_full_path), face_thumb)
                    else:
                        cv2.imwrite(str(snapshot_full_path), raw_frame)
                except Exception as e:
                    logger.error(f"Failed to save snapshot: {e}")
                    snapshot_rel_path = None

                # Persist to Database
                log_entry = AttendanceLog(
                    employee_id=emp_id,
                    punch_type=punch_type,
                    timestamp=datetime.now(timezone.utc),
                    confidence=face.similarity,
                    snapshot_path=snapshot_rel_path,
                    device_name="OpenCV Primary Kiosk"
                )
                db.add(log_entry)
                db.commit()
                db.refresh(log_entry)

                # Update in-memory cooldown
                self.cooldown_tracker[emp_id] = {
                    "timestamp": current_time,
                    "type": punch_type
                }

                event_data = {
                    "id": log_entry.id,
                    "employee_id": emp_id,
                    "employee_name": face.employee_name,
                    "employee_code": face.employee_code,
                    "department": face.department,
                    "punch_type": punch_type,
                    "confidence": f"{int(face.similarity * 100)}%",
                    "timestamp": format_local_timestamp(log_entry.timestamp, "%H:%M:%S"),
                    "date": format_local_timestamp(log_entry.timestamp, "%Y-%m-%d"),
                    "snapshot_url": f"/data/{snapshot_rel_path}" if snapshot_rel_path else None
                }

                # Push to recent events ticker
                self.recent_events.insert(0, event_data)
                if len(self.recent_events) > self.max_recent_events:
                    self.recent_events.pop()

                new_punches.append(event_data)
                logger.info(f"Attendance recorded: {face.employee_name} ({punch_type}) with confidence {face.similarity:.2f}")

        except Exception as e:
            logger.error(f"Error recording attendance: {e}")
            db.rollback()
        finally:
            db.close()

        return new_punches

    def _determine_punch_type(self, db: Session, employee_id: int) -> str:
        """
        Determine if the action is CHECK_IN or CHECK_OUT.
        - If operational punch_mode is explicitly 'CHECK_IN' or 'CHECK_OUT', enforce it.
        - If 'AUTO', alternate based on the employee's most recent punch within 14 hours.
        """
        if self.punch_mode in ["CHECK_IN", "CHECK_OUT"]:
            return self.punch_mode

        now = datetime.now(timezone.utc)
        recent_cutoff = now - timedelta(hours=14)

        last_log = (
            db.query(AttendanceLog)
            .filter(
                AttendanceLog.employee_id == employee_id,
                AttendanceLog.timestamp >= recent_cutoff
            )
            .order_by(AttendanceLog.timestamp.desc())
            .first()
        )

        if not last_log or last_log.punch_type == "CHECK_OUT":
            return "CHECK_IN"
        else:
            return "CHECK_OUT"

    def _load_recent_from_db(self):
        """Pre-populate recent events cache from DB upon cold start."""
        db: Session = SessionLocal()
        try:
            logs = (
                db.query(AttendanceLog)
                .outerjoin(Employee)
                .order_by(AttendanceLog.timestamp.desc())
                .limit(self.max_recent_events)
                .all()
            )
            seeded = []
            for log in logs:
                seeded.append({
                    "id": log.id,
                    "employee_id": log.employee_id,
                    "employee_name": log.employee.full_name if log.employee else "Unknown",
                    "employee_code": log.employee.employee_code if log.employee else "-",
                    "department": log.employee.department if log.employee else "-",
                    "punch_type": log.punch_type,
                    "confidence": f"{int(log.confidence * 100)}%",
                    "timestamp": format_local_timestamp(log.timestamp, "%H:%M:%S"),
                    "date": format_local_timestamp(log.timestamp, "%Y-%m-%d"),
                    "snapshot_url": f"/data/{log.snapshot_path}" if log.snapshot_path else None
                })
            self.recent_events = seeded
        except Exception as e:
            logger.error(f"Error pre-seeding recent events from DB: {e}")
        finally:
            db.close()

    def get_recent_punches(self) -> List[dict]:
        """Return the latest punches for the kiosk live ticker."""
        if not self.recent_events:
            self._load_recent_from_db()
        return list(self.recent_events)

attendance_engine = AttendanceEngine()
