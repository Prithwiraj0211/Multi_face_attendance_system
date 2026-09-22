import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
WEIGHTS_DIR = BACKEND_DIR / "weights"

# Ensure runtime directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
WEIGHTS_DIR.mkdir(parents=True, exist_ok=True)

# Load .env file
load_dotenv(BASE_DIR / ".env")

class Settings:
    PROJECT_NAME: str = "Multi-Face AI Attendance System"
    VERSION: str = "1.0.0"
    API_PREFIX: str = "/api"
    
    # Directory paths
    BASE_DIR: Path = BASE_DIR
    BACKEND_DIR: Path = BACKEND_DIR
    DATA_DIR: Path = DATA_DIR
    UPLOADS_DIR: Path = UPLOADS_DIR
    WEIGHTS_DIR: Path = WEIGHTS_DIR
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "super-secret-production-key-change-in-env-9482938492834")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")) # 24 hours
    
    # Default Admin
    DEFAULT_ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    DEFAULT_ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    
    # Database
    # Default is PostgreSQL. If Postgres is unavailable at startup, the system gracefully falls back to SQLite
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/attendance_db"
    )
    SQLITE_FALLBACK_URL: str = f"sqlite:///{DATA_DIR / 'attendance.db'}"
    
    # Camera & Vision
    CAMERA_INDEX: int = int(os.getenv("CAMERA_INDEX", "0"))
    FRAME_WIDTH: int = int(os.getenv("FRAME_WIDTH", "640"))
    FRAME_HEIGHT: int = int(os.getenv("FRAME_HEIGHT", "480"))
    CAMERA_FPS: int = int(os.getenv("CAMERA_FPS", "30"))
    
    # AI Thresholds
    # SFace cosine similarity threshold (Standard recommended by OpenCV is 0.363, values >= 0.38 indicate matching identity)
    FACE_MATCH_THRESHOLD: float = float(os.getenv("FACE_MATCH_THRESHOLD", "0.38"))
    FACE_DETECTOR_CONF_THRESHOLD: float = float(os.getenv("FACE_DETECTOR_CONF_THRESHOLD", "0.60"))
    
    # Attendance Logic
    PUNCH_COOLDOWN_SECONDS: int = int(os.getenv("PUNCH_COOLDOWN_SECONDS", "300")) # 5 min debounce
    AUTO_CHECKOUT_HOURS: int = int(os.getenv("AUTO_CHECKOUT_HOURS", "12"))
    
    # Model Weights paths
    YUNET_MODEL_PATH: Path = WEIGHTS_DIR / "face_detection_yunet_2023mar.onnx"
    SFACE_MODEL_PATH: Path = WEIGHTS_DIR / "face_recognition_sface_2021dec.onnx"

settings = Settings()
