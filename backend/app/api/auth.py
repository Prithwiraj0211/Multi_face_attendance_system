from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from backend.app.core.datetime_utils import format_local_timestamp
from backend.app.core.security import (
    verify_password, hash_password, create_access_token, get_current_admin_user
)
from backend.app.db.database import get_db, get_active_db_info
from backend.app.db.models import AdminUser

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

class ProfileUpdateRequest(BaseModel):
    username: Optional[str] = None
    full_name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None

class CreateAdminRequest(BaseModel):
    username: str
    password: str
    full_name: Optional[str] = "Administrator"
    role: Optional[str] = "ADMIN"

@router.post("/login")
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    """Authenticate administrator and issue JWT token."""
    user = db.query(AdminUser).filter(AdminUser.username == payload.username.strip()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )

    token = create_access_token(data={"sub": user.username, "role": user.role})

    # Set auth cookie for dashboard browser navigation
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=86400,
        samesite="lax",
        path="/"
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role
        }
    }

@router.post("/logout")
def logout(response: Response):
    """Clear session cookie."""
    response.delete_cookie(key="access_token", path="/")
    return {"message": "Logged out successfully"}

@router.get("/me")
def get_current_user_profile(
    current_user: dict = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Retrieve current logged in admin profile and system database status."""
    user = db.query(AdminUser).filter(AdminUser.username == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "role": user.role,
        "created_at": format_local_timestamp(user.created_at, "%Y-%m-%d %H:%M:%S") if user.created_at else "",
        "database": get_active_db_info()
    }

@router.put("/profile")
def update_profile(
    payload: ProfileUpdateRequest,
    response: Response,
    current_user: dict = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Update username, full name, and/or password for the authenticated administrator."""
    user = db.query(AdminUser).filter(AdminUser.username == current_user["sub"]).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # If updating password
    if payload.new_password:
        if not payload.current_password:
            raise HTTPException(status_code=400, detail="Current password is required to change password.")
        if not verify_password(payload.current_password, user.hashed_password):
            raise HTTPException(status_code=400, detail="Incorrect current password.")
        if len(payload.new_password) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters long.")
        user.hashed_password = hash_password(payload.new_password)

    # If updating username
    username_changed = False
    if payload.username and payload.username.strip() != user.username:
        new_username = payload.username.strip()
        if len(new_username) < 3:
            raise HTTPException(status_code=400, detail="Username must be at least 3 characters long.")
        # Check uniqueness
        existing = db.query(AdminUser).filter(
            AdminUser.username == new_username,
            AdminUser.id != user.id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail=f"Username '{new_username}' is already taken.")
        user.username = new_username
        username_changed = True

    # If updating full name
    if payload.full_name is not None:
        user.full_name = payload.full_name.strip() or user.full_name

    db.commit()
    db.refresh(user)

    # If username changed, issue a refreshed token and update session cookie
    token = None
    if username_changed:
        token = create_access_token(data={"sub": user.username, "role": user.role})
        response.set_cookie(
            key="access_token",
            value=f"Bearer {token}",
            httponly=True,
            max_age=86400,
            samesite="lax",
            path="/"
        )

    return {
        "message": "Profile updated successfully.",
        "username_changed": username_changed,
        "access_token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role
        }
    }

@router.get("/admins")
def list_admins(
    current_user: dict = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """List all registered administrator accounts."""
    admins = db.query(AdminUser).order_by(AdminUser.created_at.asc()).all()
    return [
        {
            "id": a.id,
            "username": a.username,
            "full_name": a.full_name,
            "role": a.role,
            "created_at": format_local_timestamp(a.created_at, "%Y-%m-%d %H:%M") if a.created_at else "Initial",
            "is_current": a.username == current_user["sub"]
        }
        for a in admins
    ]

@router.post("/admins")
def create_admin(
    payload: CreateAdminRequest,
    current_user: dict = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Create a new administrator account."""
    clean_username = payload.username.strip()
    if len(clean_username) < 3:
        raise HTTPException(status_code=400, detail="Username must be at least 3 characters.")
    if len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    existing = db.query(AdminUser).filter(AdminUser.username == clean_username).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Username '{clean_username}' already exists.")

    new_admin = AdminUser(
        username=clean_username,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip() if payload.full_name else "Administrator",
        role=payload.role if payload.role in ["SUPER_ADMIN", "ADMIN"] else "ADMIN"
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)

    return {
        "message": f"Administrator '{new_admin.username}' created successfully.",
        "admin": {
            "id": new_admin.id,
            "username": new_admin.username,
            "full_name": new_admin.full_name,
            "role": new_admin.role,
            "created_at": format_local_timestamp(new_admin.created_at, "%Y-%m-%d %H:%M") if new_admin.created_at else ""
        }
    }

@router.delete("/admins/{admin_id}")
def delete_admin(
    admin_id: int,
    current_user: dict = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete an administrator account."""
    target = db.query(AdminUser).filter(AdminUser.id == admin_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Administrator not found.")

    if target.username == current_user["sub"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own active administrator account.")

    total_admins = db.query(AdminUser).count()
    if total_admins <= 1:
        raise HTTPException(status_code=400, detail="Cannot delete the only remaining administrator account.")

    deleted_name = target.username
    db.delete(target)
    db.commit()

    return {"message": f"Administrator '{deleted_name}' deleted successfully."}
