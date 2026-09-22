import os
import uuid
import logging
from typing import List, Optional
import cv2
import numpy as np
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from backend.app.core.config import settings
from backend.app.core.security import get_current_admin_user
from backend.app.db.database import get_db
from backend.app.db.models import Employee, FaceEmbedding, AttendanceLog
from backend.app.ml.camera import camera_manager
from backend.app.ml.face_engine import face_engine

logger = logging.getLogger("attendance.api.employees")
router = APIRouter()

AVATARS_DIR = settings.DATA_DIR / "avatars"
AVATARS_DIR.mkdir(parents=True, exist_ok=True)

class EmployeeCreateRequest(BaseModel):
    employee_code: str
    first_name: str
    last_name: Optional[str] = ""
    email: Optional[str] = None
    department: Optional[str] = "Engineering"
    designation: Optional[str] = "Specialist"

class EmployeeResponse(BaseModel):
    id: int
    employee_code: str
    first_name: str
    last_name: str
    full_name: str
    email: Optional[str]
    department: str
    designation: str
    avatar_url: Optional[str]
    has_face_enrolled: bool
    is_active: bool

    class Config:
        from_attributes = True

@router.get("/", response_model=List[EmployeeResponse])
def list_employees(
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user)
):
    """List all registered employees with enrollment status."""
    employees = db.query(Employee).order_by(Employee.id.desc()).all()
    results = []
    for emp in employees:
        results.append(EmployeeResponse(
            id=emp.id,
            employee_code=emp.employee_code,
            first_name=emp.first_name,
            last_name=emp.last_name or "",
            full_name=emp.full_name,
            email=emp.email,
            department=emp.department,
            designation=emp.designation,
            avatar_url=f"/data/{emp.avatar_path}" if emp.avatar_path else None,
            has_face_enrolled=len(emp.embeddings) > 0,
            is_active=emp.is_active
        ))
    return results

@router.post("/", response_model=EmployeeResponse)
def create_employee(
    payload: EmployeeCreateRequest,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user)
):
    """Create a new employee profile with strict input validation."""
    code = payload.employee_code.strip().upper()
    first = payload.first_name.strip()
    last = payload.last_name.strip() if payload.last_name else ""
    email = payload.email.strip() if payload.email else None

    if not code:
        raise HTTPException(status_code=400, detail="Employee code cannot be empty.")
    if not first:
        raise HTTPException(status_code=400, detail="First name cannot be empty.")

    # Check code uniqueness
    existing = db.query(Employee).filter(Employee.employee_code == code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Employee code '{code}' already exists."
        )

    # Check email uniqueness if provided
    if email:
        existing_email = db.query(Employee).filter(Employee.email == email).first()
        if existing_email:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email address '{email}' is already registered."
            )

    employee = Employee(
        employee_code=code,
        first_name=first,
        last_name=last,
        email=email,
        department=payload.department.strip() if payload.department else "Engineering",
        designation=payload.designation.strip() if payload.designation else "Specialist",
        is_active=True
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)

    return EmployeeResponse(
        id=employee.id,
        employee_code=employee.employee_code,
        first_name=employee.first_name,
        last_name=employee.last_name or "",
        full_name=employee.full_name,
        email=employee.email,
        department=employee.department,
        designation=employee.designation,
        avatar_url=None,
        has_face_enrolled=False,
        is_active=True
    )

@router.post("/{employee_id}/capture-camera")
def capture_face_from_live_camera(
    employee_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user)
):
    """
    1-Click Face Enrollment from the live OpenCV camera.
    Freezes the currently centered face from the camera feed, extracts 128D embedding,
    saves cropped portrait face as avatar, and updates the in-memory AI cache immediately.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    raw_frame = camera_manager.get_latest_frame()
    if raw_frame is None or not camera_manager.camera_connected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hardware camera is not currently connected or capturing."
        )

    # Extract single face feature and portrait crop
    success, vector, message, face_crop = face_engine.extract_single_face_feature(raw_frame)
    if not success or vector is None:
        raise HTTPException(status_code=400, detail=message)

    # Save avatar image (use cropped portrait if available)
    avatar_filename = f"avatar_{employee.id}_{uuid.uuid4().hex[:6]}.jpg"
    avatar_rel_path = f"avatars/{avatar_filename}"
    avatar_full_path = AVATARS_DIR / avatar_filename

    save_img = face_crop if (face_crop is not None and face_crop.size > 0) else raw_frame
    cv2.imwrite(str(avatar_full_path), save_img)
    employee.avatar_path = avatar_rel_path

    # Save embedding record
    embedding_record = FaceEmbedding(
        employee_id=employee.id,
        algorithm="SFace",
        enrolled_via="CAMERA"
    )
    embedding_record.set_embedding(vector)
    db.add(embedding_record)
    db.commit()

    # Instant refresh in-memory face cache
    face_engine.reload_embeddings_from_db(db)

    return {
        "success": True,
        "message": f"Face enrolled for {employee.full_name}!",
        "avatar_url": f"/data/{avatar_rel_path}"
    }

@router.post("/{employee_id}/upload-face")
async def upload_face_photo(
    employee_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user)
):
    """
    Upload an employee image file (JPEG/PNG), detect face, extract embedding,
    save cropped portrait avatar, and update the in-memory AI cache immediately.
    """
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    contents = await file.read()
    nparr = np.frombuffer(contents, np.uint8)
    image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if image is None:
        raise HTTPException(status_code=400, detail="Invalid image file format")

    # Extract single face feature and portrait crop
    success, vector, message, face_crop = face_engine.extract_single_face_feature(image)
    if not success or vector is None:
        raise HTTPException(status_code=400, detail=message)

    # Save avatar image
    avatar_filename = f"avatar_{employee.id}_{uuid.uuid4().hex[:6]}.jpg"
    avatar_rel_path = f"avatars/{avatar_filename}"
    avatar_full_path = AVATARS_DIR / avatar_filename

    save_img = face_crop if (face_crop is not None and face_crop.size > 0) else image
    cv2.imwrite(str(avatar_full_path), save_img)
    employee.avatar_path = avatar_rel_path

    # Save embedding record
    embedding_record = FaceEmbedding(
        employee_id=employee.id,
        algorithm="SFace",
        enrolled_via="UPLOAD"
    )
    embedding_record.set_embedding(vector)
    db.add(embedding_record)
    db.commit()

    # Instant refresh in-memory face cache
    face_engine.reload_embeddings_from_db(db)

    return {
        "success": True,
        "message": f"Face photo enrolled for {employee.full_name}!",
        "avatar_url": f"/data/{avatar_rel_path}"
    }

@router.delete("/{employee_id}")
def delete_employee(
    employee_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user)
):
    """Delete an employee profile and associated biometric embeddings safely."""
    employee = db.query(Employee).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    emp_name = employee.full_name
    avatar_path = employee.avatar_path

    db.delete(employee)
    db.commit()

    # Clean up avatar on disk if present
    if avatar_path:
        disk_path = settings.DATA_DIR / avatar_path
        if disk_path.exists():
            try:
                disk_path.unlink()
            except Exception as e:
                logger.warning(f"Could not remove avatar file {disk_path}: {e}")

    # Refresh AI cache
    face_engine.reload_embeddings_from_db(db)
    return {"success": True, "message": f"Employee {emp_name} deleted."}
