from fastapi import APIRouter
from backend.app.api import auth, employees, attendance, stream, ws

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(employees.router, prefix="/employees", tags=["Employees"])
api_router.include_router(attendance.router, prefix="/attendance", tags=["Attendance"])
api_router.include_router(stream.router, prefix="/stream", tags=["Live Stream"])
api_router.include_router(ws.router, prefix="/ws", tags=["WebSockets"])
