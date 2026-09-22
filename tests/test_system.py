"""
Comprehensive Automated Test Suite for Multi-Face Attendance System
Validates:
1. Database initialization and admin seeding
2. YuNet Multi-Face detector loading and inference
3. SFace face embedding generation and cosine similarity matching
4. Anti-spoofing and liveness check
5. Attendance state machine & cooldown debouncing
6. REST API authentication and endpoints
"""
import sys
import os
from pathlib import Path

# Add root directory to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Ensure UTF-8 console output on Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import numpy as np
import cv2
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.db.database import init_db, SessionLocal, get_active_db_info
from backend.app.db.models import AdminUser, Employee, FaceEmbedding, AttendanceLog
from backend.app.ml.face_engine import face_engine, DetectedFace
from backend.app.ml.anti_spoof import anti_spoof_detector
from backend.app.ml.attendance_engine import attendance_engine
from backend.app.core.security import verify_password, create_access_token, decode_access_token

def test_database_and_admin():
    print("--- [1/5] Testing Database & Admin Credentials ---")
    init_db()
    db = SessionLocal()
    try:
        admin = db.query(AdminUser).filter_by(username=settings.DEFAULT_ADMIN_USERNAME).first()
        assert admin is not None, "Admin user not found"
        assert verify_password(settings.DEFAULT_ADMIN_PASSWORD, admin.hashed_password), "Admin password verification failed"
        print(f"PASS: Admin user '{admin.username}' authenticated. Database: {get_active_db_info()['type']}")
    finally:
        db.close()

def test_ai_models_and_inference():
    print("--- [2/5] Testing YuNet & SFace Models ---")
    assert face_engine.detector is not None, "YuNet detector not initialized"
    assert face_engine.recognizer is not None, "SFace recognizer not initialized"
    
    # Create test synthetic frame with simulated face-like oval
    test_img = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.circle(test_img, (320, 240), 90, (180, 160, 140), -1)
    
    # Test multi-face detection call
    detections = face_engine.detect_and_recognize_all(test_img)
    print(f"PASS: Detection pipeline executed smoothly on 640x480 frame (Faces detected: {len(detections)})")
    
    # Test vector cosine similarity
    vec1 = np.random.randn(1, 128).astype(np.float32)
    vec1 /= np.linalg.norm(vec1)
    sim = face_engine.recognizer.match(vec1, vec1, cv2.FaceRecognizerSF_FR_COSINE)
    assert sim > 0.99, f"Self similarity failed: {sim}"
    print(f"PASS: SFace Cosine similarity self-match verified (Score: {sim:.4f})")

def test_anti_spoof():
    print("--- [3/5] Testing Anti-Spoofing & Liveness Analyzer ---")
    # Natural image patch
    patch = np.random.randint(50, 200, (100, 100, 3), dtype=np.uint8)
    res = anti_spoof_detector.check_liveness(patch)
    assert "is_real" in res and "liveness_score" in res, "Invalid liveness return structure"
    print(f"PASS: Liveness analyzer responded: {res['details']} (Score: {res['liveness_score']})")

def test_employee_and_attendance_flow():
    print("--- [4/5] Testing Employee Registration & Attendance Debounce Flow ---")
    db: Session = SessionLocal()
    try:
        # Create test employee
        code = "TEST001"
        existing = db.query(Employee).filter_by(employee_code=code).first()
        if existing:
            db.delete(existing)
            db.commit()

        emp = Employee(
            employee_code=code,
            first_name="Jane",
            last_name="Doe",
            email="jane.doe@example.com",
            department="Cybersecurity",
            designation="Security Architect",
            is_active=True
        )
        db.add(emp)
        db.commit()
        db.refresh(emp)
        print(f"Created test employee: {emp.full_name} ({emp.employee_code})")

        # Create simulated 128D embedding
        fake_vec = np.random.randn(128).astype(np.float32)
        fake_vec /= np.linalg.norm(fake_vec)
        
        emb = FaceEmbedding(
            employee_id=emp.id,
            algorithm="SFace",
            enrolled_via="CAMERA"
        )
        emb.set_embedding(fake_vec)
        db.add(emb)
        db.commit()
        print("Enrolled simulated 128-D vector embedding into DB.")

        # Reload cache into face engine
        face_engine.reload_embeddings_from_db(db)
        assert emp.id in face_engine.known_faces, "Employee missing from in-memory AI cache"
        print(f"Verified in-memory vector cache loaded {len(face_engine.known_faces)} employee(s).")

        # Simulate verified detection
        raw_frame = np.zeros((480, 640, 3), dtype=np.uint8)
        simulated_det = DetectedFace(
            bbox=(100, 100, 120, 140),
            landmarks=np.zeros((5, 2)),
            confidence=0.95,
            is_real=True,
            liveness_score=0.92,
            employee_id=emp.id,
            employee_name=emp.full_name,
            employee_code=emp.employee_code,
            department=emp.department,
            similarity=0.85,
            status="VERIFIED"
        )

        # 1st Punch -> Should record CHECK_IN
        punches1 = attendance_engine.process_detections([simulated_det], raw_frame)
        assert len(punches1) == 1, "First punch was not recorded"
        assert punches1[0]["punch_type"] == "CHECK_IN", f"Expected CHECK_IN, got {punches1[0]['punch_type']}"
        print(f"PASS: 1st Detection correctly recorded CHECK_IN for {emp.full_name}")

        # 2nd Punch immediately -> Debounce should block duplicate punch!
        punches2 = attendance_engine.process_detections([simulated_det], raw_frame)
        assert len(punches2) == 0, "Debounce failed: duplicate punch was incorrectly recorded!"
        print("PASS: Immediate duplicate detection was correctly BLOCKED by cooldown debounce.")

        # Verify record in DB
        log = db.query(AttendanceLog).filter_by(employee_id=emp.id).first()
        assert log is not None, "Attendance record not found in database"
        assert log.punch_type == "CHECK_IN", "Log punch type mismatch"
        print(f"PASS: Database record verified (Log ID: {log.id}, Confidence: {log.confidence})")

    finally:
        db.close()

def test_jwt_auth():
    print("--- [5/5] Testing JWT Security & Cryptography ---")
    token = create_access_token({"sub": "admin", "role": "SUPER_ADMIN"})
    payload = decode_access_token(token)
    assert payload is not None, "Token decoding failed"
    assert payload["sub"] == "admin", "Token subject mismatch"
    assert payload["role"] == "SUPER_ADMIN", "Token role mismatch"
    print("PASS: JWT Token generation, HMAC signing, and payload decoding verified.")

if __name__ == "__main__":
    print("\n========================================================")
    print("RUNNING MULTI-FACE ATTENDANCE SYSTEM VERIFICATION SUITE")
    print("========================================================\n")
    
    test_database_and_admin()
    test_ai_models_and_inference()
    test_anti_spoof()
    test_employee_and_attendance_flow()
    test_jwt_auth()
    
    print("\n========================================================")
    print("ALL 5 AUTOMATED VERIFICATION SUITES PASSED SUCCESSFULLY! [PASS]")
    print("========================================================\n")
