from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_users as schemas
from typing import List
from ..customers.model_customers import DBCustomer
from .dependencies import RoleChecker, PermissionChecker

router = APIRouter(prefix="/api", tags=["users"])

from .auth_utils import verify_password, create_access_token, get_password_hash

@router.post("/auth/login")
def login(user_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(schemas.DBUser).filter(schemas.DBUser.email == user_data.email).first()
    
    # Password check only for non-customers
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if user.role != "customer":
        if not verify_password(user_data.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect password",
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
            schemas.DBRole(name="admin", description="Full System Access", permissions="*"),
            schemas.DBRole(name="manager", description="Department Manager", permissions="view_dashboard,manage_reservations,manage_customers,view_billing,manage_billing,view_notifications,approve_cash_payment,send_notifications"),
            schemas.DBRole(name="staff", description="Floor Staff", permissions="manage_reservations,manage_customers,view_billing,view_notifications,approve_cash_payment"),
        ]

        db.add_all(default_roles)
        db.commit()
    query = db.query(schemas.DBRole)
    return paginate(query, page, size)

def validate_and_expand_permissions(permissions_str: str) -> str:
    """
    Enforces hierarchical dependencies:
    - manage_reservations requires view_portal
    - manage_customers requires view_dashboard
    - manage_billing requires view_dashboard
    - dismiss_customer requires manage_reservations
    Automatically prepends or appends base permissions if missing,
    ensuring that a user can never be assigned edit rights without matching view rights.
    """
    perms = [p.strip() for p in permissions_str.split(",") if p.strip()]
    
    if "approve_cash_payment" in perms:
        if "manage_reservations" not in perms:
            perms.append("manage_reservations")
        if "view_portal" not in perms:
            perms.append("view_portal")
    if "manage_reservations" in perms and "view_portal" not in perms:
        perms.append("view_portal")
    if "manage_customers" in perms and "view_dashboard" not in perms:
        perms.append("view_dashboard")
    if "manage_billing" in perms:
        if "view_billing" not in perms:
            perms.append("view_billing")
        if "view_dashboard" not in perms:
            perms.append("view_dashboard")
    if "view_billing" in perms and "view_dashboard" not in perms:
        perms.append("view_dashboard")

    if "dismiss_customer" in perms:
        if "manage_reservations" not in perms:
            perms.append("manage_reservations")
        if "view_portal" not in perms:
            perms.append("view_portal")
            
    return ",".join(list(set(perms)))

@router.post("/roles", response_model=schemas.Role, status_code=status.HTTP_201_CREATED)
def create_role(role_in: schemas.RoleBase, db: Session = Depends(get_db), _=Depends(PermissionChecker("manage_billing"))):
    """
    Creates a new system role.
    Permissions are expanded hierarchically.
    Puts the site into configuration lock / maintenance mode first to avoid race conditions.
    """
    existing = db.query(schemas.DBRole).filter(schemas.DBRole.name == role_in.name.lower()).first()
    if existing:
        raise HTTPException(status_code=400, detail="Role with this name already exists")
    
    # 1. Engage Maintenance Lock (is_updating_config = true)
    from api.settings.model_settings import DBSetting
    lock_setting = db.query(DBSetting).filter(DBSetting.key == "is_updating_config").first()
    if not lock_setting:
        lock_setting = DBSetting(key="is_updating_config", value="true")
        db.add(lock_setting)
    else:
        lock_setting.value = "true"
    db.commit()

    try:
        # 2. Enforce ability hierarchy
        validated_perms = validate_and_expand_permissions(role_in.permissions)
        
        db_role = schemas.DBRole(
            name=role_in.name.lower(),
            description=role_in.description,
            permissions=validated_perms
        )
        db.add(db_role)
        db.commit()
        db.refresh(db_role)
        return db_role
    finally:
        # 3. Disengage Maintenance Lock (is_updating_config = false)
        lock_setting.value = "false"
        db.commit()

from pydantic import BaseModel
from typing import Optional

class RolePermissionsUpdate(BaseModel):
    permissions: str
    description: Optional[str] = None

@router.put("/roles/{name}", response_model=schemas.Role)
def update_role_permissions(
    name: str,
    req: RolePermissionsUpdate,
    db: Session = Depends(get_db),
    _ = Depends(PermissionChecker("manage_billing"))
):
    """
    Updates the permissions of an existing system role.
    Permissions are expanded hierarchically.
    Puts the site into configuration lock / maintenance mode first to avoid race conditions.
    """
    # 1. Engage Maintenance Lock (is_updating_config = true)
    from api.settings.model_settings import DBSetting
    lock_setting = db.query(DBSetting).filter(DBSetting.key == "is_updating_config").first()
    if not lock_setting:
        lock_setting = DBSetting(key="is_updating_config", value="true")
        db.add(lock_setting)
    else:
        lock_setting.value = "true"
    db.commit()

    try:
        # 2. Find and update DBRole
        role = db.query(schemas.DBRole).filter(schemas.DBRole.name == name.lower()).first()
        if not role:
            raise HTTPException(status_code=404, detail="Role not found")
            
        # 3. Enforce ability hierarchy
        validated_perms = validate_and_expand_permissions(req.permissions)
        
        role.permissions = validated_perms
        if req.description is not None:
            role.description = req.description
            
        db.commit()
        db.refresh(role)
        return role
    finally:
        # 4. Disengage Maintenance Lock (is_updating_config = false)
        lock_setting.value = "false"
        db.commit()

@router.post("/seed")
def seed_data(db: Session = Depends(get_db)):
    # Upsert Roles
    roles_data = [
        {"name": "admin", "description": "Full System Access", "permissions": "*"},
        {"name": "manager", "description": "Department Manager", "permissions": "view_dashboard,manage_reservations,manage_customers,view_billing,manage_billing,view_notifications,approve_cash_payment,send_notifications"},
        {"name": "staff", "description": "Floor Staff", "permissions": "manage_reservations,manage_customers,view_billing,view_notifications,approve_cash_payment"},
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
                db.flush()
                existing_cust = new_cust
            else:
                existing_cust.user_id = user.id

    # Seed Sample Demo Bills if missing to ensure Dashboard Chart fidelity
    from ..billing.model_bills import DBBill
    from datetime import datetime, timedelta
    if db.query(DBBill).count() == 0:
        first_cust = db.query(DBCustomer).first()
        if first_cust:
            sample_bills = [
                DBBill(customer_id=first_cust.id, amount=120.0, due_date=datetime.now() - timedelta(days=40), month_ending=datetime.now() - timedelta(days=40), pay_via="UPI", status="paid"),
                DBBill(customer_id=first_cust.id, amount=150.0, due_date=datetime.now() - timedelta(days=15), month_ending=datetime.now() - timedelta(days=15), pay_via="Cash", status="paid"),
                DBBill(customer_id=first_cust.id, amount=180.0, due_date=datetime.now(), month_ending=datetime.now(), pay_via="Credit Card", status="pending")
            ]
            for b in sample_bills:
                db.add(b)

    db.commit()
    return {"msg": "System synchronized. All roles and test users are now live."}
