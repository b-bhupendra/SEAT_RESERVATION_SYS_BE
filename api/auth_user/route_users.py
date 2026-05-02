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
    # Upsert Roles
    roles_data = [
        {"name": "admin", "description": "Full System Access", "permissions": "*"},
        {"name": "manager", "description": "Department Manager", "permissions": "view_dashboard,manage_reservations,manage_customers,manage_billing,view_notifications"},
        {"name": "staff", "description": "Floor Staff", "permissions": "manage_reservations,manage_customers,view_notifications"},
        {"name": "customer", "description": "Seat Occupant", "permissions": "view_portal,view_notifications"}
    ]
    
    for r_data in roles_data:
        role = db.query(schemas.DBRole).filter(schemas.DBRole.name == r_data["name"]).first()
        if not role:
            db.add(schemas.DBRole(**r_data))
        else:
            role.permissions = r_data["permissions"]
            role.description = r_data["description"]

    db.flush()

    # Upsert Users
    test_users = [
        {
            "email": "admin@admin.com",
            "password": "admin",
            "role": "admin",
            "full_name": "System Administrator"
        },
        {
            "email": "manager@admin.com",
            "password": "manager123",
            "role": "manager",
            "full_name": "Jane Manager"
        },
        {
            "email": "customer@example.com",
            "password": "customer123",
            "role": "customer",
            "full_name": "Robert Moore"
        }
    ]

    for u_data in test_users:
        user = db.query(schemas.DBUser).filter(schemas.DBUser.email == u_data["email"]).first()
        if not user:
            new_user = schemas.DBUser(
                email=u_data["email"],
                hashed_password=get_password_hash(u_data["password"]),
                role=u_data["role"],
                full_name=u_data["full_name"]
            )
            db.add(new_user)
            db.flush()
            user = new_user
        else:
            user.role = u_data["role"]
            user.full_name = u_data["full_name"]

        # Link DBCustomer if user is a customer
        if u_data["role"] == "customer":
            existing_cust = db.query(DBCustomer).filter(DBCustomer.email == u_data["email"]).first()
            if not existing_cust:
                new_cust = DBCustomer(
                    name=u_data["full_name"],
                    email=u_data["email"],
                    phone="9876543210",
                    user_id=user.id
                )
                db.add(new_cust)
            else:
                existing_cust.user_id = user.id

    db.commit()
    return {"msg": "System synchronized. All roles and test users are now live."}
