import json
from datetime import datetime, timezone
import numpy as np
from sqlalchemy import (
    Column, Integer, String, Boolean, Float, DateTime, ForeignKey, Text
)
from sqlalchemy.orm import relationship
from backend.app.db.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class AdminUser(Base):
    __tablename__ = "admin_users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(128), default="Administrator")
    role = Column(String(32), default="SUPER_ADMIN")
    created_at = Column(DateTime(timezone=True), default=utc_now)

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_code = Column(String(32), unique=True, index=True, nullable=False)
    first_name = Column(String(64), nullable=False)
    last_name = Column(String(64), default="")
    email = Column(String(128), unique=True, nullable=True)
    department = Column(String(64), default="Engineering")
    designation = Column(String(64), default="Specialist")
    avatar_path = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    
    # Relationships
    embeddings = relationship(
        "FaceEmbedding",
        back_populates="employee",
        cascade="all, delete-orphan"
    )
    attendance_records = relationship(
        "AttendanceLog",
        back_populates="employee",
        cascade="all, delete-orphan",
        order_by="desc(AttendanceLog.timestamp)"
    )
    
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

class FaceEmbedding(Base):
    __tablename__ = "face_embeddings"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    embedding_json = Column(Text, nullable=False) # JSON-serialized list of floats
    algorithm = Column(String(32), default="SFace")
    enrolled_via = Column(String(32), default="CAMERA") # CAMERA or UPLOAD
    created_at = Column(DateTime(timezone=True), default=utc_now)
    
    employee = relationship("Employee", back_populates="embeddings")
    
    def get_embedding(self) -> np.ndarray:
        """Convert stored JSON back into 1D numpy array float32."""
        return np.array(json.loads(self.embedding_json), dtype=np.float32)
        
    def set_embedding(self, vector: np.ndarray):
        """Convert 1D numpy array to JSON float list."""
        if isinstance(vector, np.ndarray):
            self.embedding_json = json.dumps(vector.flatten().tolist())
        else:
            self.embedding_json = json.dumps(list(vector))

class AttendanceLog(Base):
    __tablename__ = "attendance_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    punch_type = Column(String(16), nullable=False) # CHECK_IN or CHECK_OUT
    timestamp = Column(DateTime(timezone=True), default=utc_now, index=True)
    confidence = Column(Float, default=0.0)
    snapshot_path = Column(String(255), nullable=True)
    device_name = Column(String(64), default="Main Entrance Kiosk")
    
    employee = relationship("Employee", back_populates="attendance_records")
