import os
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from backend.app.core.config import settings, BASE_DIR, DATA_DIR
from backend.app.core.security import decode_access_token
from backend.app.db.database import init_db, SessionLocal, get_active_db_info
from backend.app.ml.face_engine import face_engine
from backend.app.ml.worker import vision_worker
from backend.app.api.ws import ws_manager
from backend.app.api import api_router

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("attendance.main")

# Setup Paths
FRONTEND_DIR = BASE_DIR / "frontend"
STATIC_DIR = FRONTEND_DIR / "static"
TEMPLATES_DIR = FRONTEND_DIR / "templates"

STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown management."""
    logger.info("Initializing Multi-Face AI Attendance System...")
    
    # 1. Initialize DB and default admin
    init_db()
    
    # 2. Load face embeddings into AI cache
    db = SessionLocal()
    try:
        face_engine.reload_embeddings_from_db(db)
    finally:
        db.close()
        
    # 3. Setup WebSocket loop & vision worker
    loop = asyncio.get_running_loop()
    ws_manager.set_event_loop(loop)
    vision_worker.register_broadcast_callback(ws_manager.threadsafe_broadcast)
    
    # 4. Start vision & camera processing
    vision_worker.start()
    logger.info("System startup complete. Ready for recognition.")
    
    yield
    
    # Teardown
    logger.info("Shutting down vision worker and camera...")
    vision_worker.stop()
    logger.info("Shutdown complete.")

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

# Mount Static Files and Media
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

# Register API routes
app.include_router(api_router, prefix=settings.API_PREFIX)

# Web Page Routes
@app.get("/", response_class=RedirectResponse)
def index():
    """Default root redirects to the Live Attendance Kiosk."""
    return RedirectResponse(url="/kiosk")

@app.get("/kiosk", response_class=HTMLResponse)
def kiosk_page(request: Request):
    """Full-Screen Live Multi-Face Attendance Terminal."""
    return templates.TemplateResponse(
        "kiosk.html",
        {
            "request": request,
            "project_name": settings.PROJECT_NAME,
            "version": settings.VERSION
        }
    )

@app.get("/admin/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Admin Login Portal."""
    token = request.cookies.get("access_token")
    if token:
        if token.startswith("Bearer "):
            token = token[7:]
        payload = decode_access_token(token)
        if payload:
            return RedirectResponse(url="/admin")

    return templates.TemplateResponse(
        "login.html",
        {"request": request, "project_name": settings.PROJECT_NAME}
    )

@app.get("/admin", response_class=HTMLResponse)
def admin_dashboard(request: Request):
    """Admin Control Center & Analytics Dashboard."""
    token = request.cookies.get("access_token")
    if not token:
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)

    if token.startswith("Bearer "):
        token = token[7:]

    payload = decode_access_token(token)
    if not payload:
        response = RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
        response.delete_cookie(key="access_token", path="/")
        return response

    admin_name = payload.get("sub", "Admin")

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "admin_user": admin_name,
            "project_name": settings.PROJECT_NAME,
            "db_info": get_active_db_info()
        }
    )
