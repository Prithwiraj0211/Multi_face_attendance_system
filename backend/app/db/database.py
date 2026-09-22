import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.app.core.config import settings

logger = logging.getLogger("attendance.db")

Base = declarative_base()

ACTIVE_DB_TYPE = "PostgreSQL"
engine = None
SessionLocal = None

def initialize_engine():
    global engine, SessionLocal, ACTIVE_DB_TYPE
    
    # Try PostgreSQL first
    try:
        pg_engine = create_engine(
            settings.DATABASE_URL,
            pool_pre_ping=True,
            connect_args={"connect_timeout": 3}
        )
        # Test connection
        with pg_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine = pg_engine
        ACTIVE_DB_TYPE = "PostgreSQL"
        logger.info(f"Connected to primary database: {ACTIVE_DB_TYPE}")
    except Exception as e:
        logger.warning(
            f"PostgreSQL connection to '{settings.DATABASE_URL}' failed: {e}. "
            f"Activating self-healing SQLite fallback at '{settings.SQLITE_FALLBACK_URL}'."
        )
        # Fallback to SQLite
        engine = create_engine(
            settings.SQLITE_FALLBACK_URL,
            connect_args={"check_same_thread": False}
        )
        ACTIVE_DB_TYPE = "SQLite"
        
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine

# Initialize on import
initialize_engine()

def get_db():
    """Dependency for obtaining a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_active_db_info() -> dict:
    """Return current active database information."""
    return {
        "type": ACTIVE_DB_TYPE,
        "is_postgres": ACTIVE_DB_TYPE == "PostgreSQL",
        "url": settings.DATABASE_URL if ACTIVE_DB_TYPE == "PostgreSQL" else settings.SQLITE_FALLBACK_URL
    }

def init_db():
    """Create all database tables and seed default admin user if not present."""
    from backend.app.db import models
    from backend.app.core.security import hash_password
    
    Base.metadata.create_all(bind=engine)
    
    # Seed default admin user
    db = SessionLocal()
    try:
        admin = db.query(models.AdminUser).filter_by(username=settings.DEFAULT_ADMIN_USERNAME).first()
        if not admin:
            admin = models.AdminUser(
                username=settings.DEFAULT_ADMIN_USERNAME,
                hashed_password=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
                full_name="System Administrator",
                role="SUPER_ADMIN"
            )
            db.add(admin)
            db.commit()
            logger.info(f"Default admin created with username: '{settings.DEFAULT_ADMIN_USERNAME}'")
    finally:
        db.close()
