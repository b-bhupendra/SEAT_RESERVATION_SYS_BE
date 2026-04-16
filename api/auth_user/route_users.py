from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_users as schemas
from typing import List
from ..customers.model_customers import DBCustomer
from .dependencies import RoleChecker

router = APIRouter(prefix="/api", tags=["users"])

from .auth_utils import verify_password, create_access_token, get_password_hash

@router.post("/auth/login")
def login(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(schemas.DBUser).filter(schemas.DBUser.email == user_data.email).first()
    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    
    # Fetch permissions for the role
    role_data = db.query(schemas.DBRole).filter(schemas.DBRole.name == user.role).first()
    permissions = role_data.permissions if role_data else ""

    return {
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "full_name": user.full_name,
            "permissions": permissions
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

@router.post("/roles", response_model=schemas.Role, status_code=status.HTTP_201_CREATED)
def create_role(role_in: schemas.RoleBase, db: Session = Depends(get_db), _=Depends(RoleChecker(["admin"]))):
    """
    Creates a new system role. 
    Permissions should be a comma-separated string of keys (e.g. 'view_dashboard,manage_billing').
    """
    existing = db.query(schemas.DBRole).filter(schemas.DBRole.name == role_in.name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role with this name already exists")
    
    db_role = schemas.DBRole(**role_in.dict())
    db_role.name = db_role.name.lower() # Normalize names
    db.add(db_role)
    db.commit()
    db.refresh(db_role)
    return db_role

@router.post("/seed")
def seed_data(db: Session = Depends(get_db)):
    # Seed roles if empty
    if not db.query(schemas.DBRole).first():
        roles = [
            {"name": "admin", "description": "Full System Access", "permissions": "*"},
            {"name": "manager", "description": "Department Manager", "permissions": "view_dashboard,manage_reservations,manage_customers,manage_billing,view_notifications"},
            {"name": "staff", "description": "Floor Staff", "permissions": "manage_reservations,manage_customers,view_notifications"},
            {"name": "customer", "description": "Seat Occupant", "permissions": "view_portal,view_notifications"}
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

        customer_user = schemas.DBUser(
            email="customer@example.com",
            hashed_password=get_password_hash("customer123"),
            role="customer",
            full_name="Robert Moore"
        )
        db.add(customer_user)
        db.flush()

        # Link DBCustomer to DBUser
        existing_cust = db.query(DBCustomer).filter(DBCustomer.email == "customer@example.com").first()
        if not existing_cust:
            new_cust = DBCustomer(
                name="Robert Moore",
                email="customer@example.com",
                phone="9876543210",
                user_id=customer_user.id
            )
            db.add(new_cust)
        else:
            existing_cust.user_id = customer_user.id

    db.commit()
    return {"msg": "User and role data seeded. Use admin@admin.com / admin"}
