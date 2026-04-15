from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_users as schemas
from typing import List

router = APIRouter(prefix="/api", tags=["users"])

from .auth_utils import verify_password, create_access_token, get_password_hash

@router.post("/auth/login")
def login(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    user = db.query(schemas.DBUser).filter(schemas.DBUser.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name
        },
        "access_token": access_token,
        "token_type": "bearer"
    }

from ..pagination import PaginatedResponse, paginate

@router.get("/roles", response_model=PaginatedResponse[schemas.Role])
def get_roles(page: int = 1, size: int = 10, db: Session = Depends(get_db)):
    # Auto-seed default roles if the table is empty
    if not db.query(schemas.DBRole).first():
        default_roles = [
            schemas.DBRole(name="admin", description="Full System Access", permissions="all"),
            schemas.DBRole(name="manager", description="Department Manager", permissions="read,write,notify"),
            schemas.DBRole(name="staff", description="Floor Staff", permissions="read,write_reservations"),
        ]
        db.add_all(default_roles)
        db.commit()
    query = db.query(schemas.DBRole)
    return paginate(query, page, size)

@router.post("/seed")
def seed_data(db: Session = Depends(get_db)):
    # Seed roles if empty
    if not db.query(schemas.DBRole).first():
        roles = [
            {"name": "admin", "description": "Full System Access", "permissions": "all"},
            {"name": "manager", "description": "Department Manager", "permissions": "read,write,notify"},
            {"name": "staff", "description": "Floor Staff", "permissions": "read,write_reservations"}
        ]
        for r in roles:
            db.add(schemas.DBRole(**r))
    
    # Seed default admin if empty
    if not db.query(schemas.DBUser).filter(schemas.DBUser.email == "admin@admin.com").first():
        admin_user = schemas.DBUser(
            email="admin@admin.com",
            hashed_password=get_password_hash("admin"),
            role="admin",
            full_name="System Admin"
        )
        db.add(admin_user)
        
        staff_user = schemas.DBUser(
            email="staff@admin.com",
            hashed_password=get_password_hash("staff123"),
            role="staff",
            full_name="Operations Staff"
        )
        db.add(staff_user)

        manager_user = schemas.DBUser(
            email="manager@admin.com",
            hashed_password=get_password_hash("manager123"),
            role="manager",
            full_name="Department Manager"
        )
        db.add(manager_user)

    db.commit()
    return {"msg": "User and role data seeded. Use admin@admin.com / admin"}
