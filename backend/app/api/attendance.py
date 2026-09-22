import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.app.core.datetime_utils import format_local_timestamp, get_local_day_utc_bounds
from backend.app.core.security import get_current_admin_user
from backend.app.db.database import get_db, get_active_db_info
from backend.app.db.models import AttendanceLog, Employee
from backend.app.ml.attendance_engine import attendance_engine

router = APIRouter()

@router.get("/stats")
def get_attendance_stats(
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user)
):
    """Retrieve high-level KPI dashboard metrics based on the current local calendar day."""
    today_start_utc, today_end_utc = get_local_day_utc_bounds()
    
    total_employees = db.query(Employee).filter(Employee.is_active == True).count()
    
    # Today's unique checked-in employees
    today_checkins = (
        db.query(AttendanceLog.employee_id)
        .filter(
            AttendanceLog.timestamp >= today_start_utc,
            AttendanceLog.timestamp < today_end_utc,
            AttendanceLog.punch_type == "CHECK_IN"
        )
        .distinct()
        .count()
    )
    
    # Today's unique check-outs
    today_checkouts = (
        db.query(AttendanceLog.employee_id)
        .filter(
            AttendanceLog.timestamp >= today_start_utc,
            AttendanceLog.timestamp < today_end_utc,
            AttendanceLog.punch_type == "CHECK_OUT"
        )
        .distinct()
        .count()
    )
    
    # Currently on site: checked in but not checked out yet
    currently_present = max(0, today_checkins - today_checkouts)
    
    # Recent logs
    recent_logs = (
        db.query(AttendanceLog)
        .order_by(AttendanceLog.timestamp.desc())
        .limit(10)
        .all()
    )
    
    recent_list = []
    for log in recent_logs:
        recent_list.append({
            "id": log.id,
            "employee_id": log.employee_id,
            "employee_name": log.employee.full_name if log.employee else "Unknown",
            "employee_code": log.employee.employee_code if log.employee else "-",
            "department": log.employee.department if log.employee else "-",
            "punch_type": log.punch_type,
            "timestamp": format_local_timestamp(log.timestamp),
            "confidence": f"{int(log.confidence * 100)}%",
            "snapshot_url": f"/data/{log.snapshot_path}" if log.snapshot_path else None
        })

    return {
        "total_employees": total_employees,
        "today_checkins": today_checkins,
        "today_checkouts": today_checkouts,
        "currently_present": currently_present,
        "attendance_rate": f"{(today_checkins / max(1, total_employees)) * 100:.1f}%",
        "recent_logs": recent_list,
        "database": get_active_db_info()
    }

@router.get("/logs")
def get_attendance_logs(
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user),
    date: Optional[str] = Query(None, description="Format YYYY-MM-DD"),
    punch_type: Optional[str] = Query(None, description="CHECK_IN or CHECK_OUT"),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0)
):
    """Query paginated attendance logs with optional local date and punch type filtering."""
    query = db.query(AttendanceLog).outerjoin(Employee)
    
    if date:
        try:
            start_utc, end_utc = get_local_day_utc_bounds(date)
            query = query.filter(
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
            
    if punch_type and punch_type in ["CHECK_IN", "CHECK_OUT"]:
        query = query.filter(AttendanceLog.punch_type == punch_type)
        
    total_count = query.count()
    logs = query.order_by(AttendanceLog.timestamp.desc()).offset(offset).limit(limit).all()
    
    items = []
    for log in logs:
        items.append({
            "id": log.id,
            "employee_id": log.employee_id,
            "employee_name": log.employee.full_name if log.employee else "Unknown",
            "employee_code": log.employee.employee_code if log.employee else "-",
            "department": log.employee.department if log.employee else "-",
            "punch_type": log.punch_type,
            "timestamp": format_local_timestamp(log.timestamp),
            "confidence": f"{int(log.confidence * 100)}%",
            "snapshot_url": f"/data/{log.snapshot_path}" if log.snapshot_path else None
        })
        
    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "items": items
    }

@router.get("/export-csv")
def export_attendance_csv(
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_admin_user),
    date: Optional[str] = Query(None),
    punch_type: Optional[str] = Query(None)
):
    """Download attendance logs as a formatted CSV spreadsheet with localized timestamps."""
    query = db.query(AttendanceLog).outerjoin(Employee).order_by(AttendanceLog.timestamp.desc())
    
    if date:
        try:
            start_utc, end_utc = get_local_day_utc_bounds(date)
            query = query.filter(
                AttendanceLog.timestamp >= start_utc,
                AttendanceLog.timestamp < end_utc
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    if punch_type and punch_type in ["CHECK_IN", "CHECK_OUT"]:
        query = query.filter(AttendanceLog.punch_type == punch_type)

    logs = query.all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Log ID", "Employee Code", "Full Name", "Department",
        "Punch Type", "Timestamp", "Confidence Score", "Device"
    ])
    
    for log in logs:
        writer.writerow([
            log.id,
            log.employee.employee_code if log.employee else "",
            log.employee.full_name if log.employee else "Unknown",
            log.employee.department if log.employee else "",
            log.punch_type,
            format_local_timestamp(log.timestamp),
            f"{int(log.confidence * 100)}%",
            log.device_name
        ])
        
    csv_data = output.getvalue()
    filter_suffix = f"_{punch_type.lower()}" if punch_type else ""
    filename = f"attendance_export_{date or 'all'}{filter_suffix}.csv"
    
    return Response(
        content=csv_data,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@router.get("/ticker")
def get_live_ticker():
    """Public endpoint for Kiosk to pull recent punch notifications."""
    return attendance_engine.get_recent_punches()

class PunchModePayload(BaseModel):
    mode: str

@router.get("/mode")
def get_punch_mode():
    """Retrieve operational kiosk punch mode: AUTO, CHECK_IN, or CHECK_OUT."""
    return {"mode": attendance_engine.punch_mode}

@router.post("/mode")
def set_punch_mode(payload: PunchModePayload):
    """Set operational kiosk punch mode."""
    target_mode = payload.mode.upper().strip()
    if target_mode not in ["AUTO", "CHECK_IN", "CHECK_OUT"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid mode. Choose from: AUTO, CHECK_IN, CHECK_OUT"
        )
    attendance_engine.punch_mode = target_mode
    attendance_engine.cooldown_tracker.clear()
    return {
        "mode": attendance_engine.punch_mode,
        "message": f"Kiosk punch mode set to {target_mode}"
    }
