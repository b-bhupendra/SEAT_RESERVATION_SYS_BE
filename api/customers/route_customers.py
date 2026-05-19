from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_customers as schemas
from ..auth_user.dependencies import RoleChecker, get_allowed_orgs, PermissionChecker
from typing import List, Optional
from datetime import datetime, timedelta
from ..supabase_utils import upload_base64_to_supabase
from ..reservations.model_reservations import DBReservation, Reservation

router = APIRouter(prefix="/api", tags=["customers"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff"]

from ..auth_user.auth_utils import get_password_hash
from ..auth_user.model_users import DBUser
from ..pagination import PaginatedResponse, paginate
from fastapi import Query as FastAPIQuery

@router.get("/me/reservation")
async def get_my_reservation(
    db: Session = Depends(get_db),
    user_payload: dict = Depends(RoleChecker(["customer", "admin"]))
):
    """
    Retrieves the logged-in customer's active reservation or grace period status.
    """
    from ..reservations.route_seats import cleanup_expired_holds
    from ..settings.model_settings import DBSetting
    from ..reservations.loyalty import calculate_loyalty_and_grace, calculate_fine_and_total
    
    # Run dynamic expiration check first
    cleanup_expired_holds(db)

    user_email = user_payload.get("sub")
    customer = db.query(schemas.DBCustomer).filter(schemas.DBCustomer.email == user_email).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer record not found for this user.")
        
    reservation = db.query(DBReservation).filter(
        DBReservation.customer_id == customer.id,
        DBReservation.status.in_(["paid", "pending"])
    ).order_by(DBReservation.created_at.desc()).first()
    
    # Check grace period if reservation is expired
    is_in_grace = False
    grace_expiry = None
    loyalty_tier = "Bronze"
    grace_days = 2
    fine_amount = 0.0
    
    if reservation and reservation.status == "paid" and reservation.end_date and datetime.utcnow() > reservation.end_date:
        loyalty_tier, grace_days = calculate_loyalty_and_grace(db, customer.id)
        expiry_deadline = reservation.end_date + timedelta(days=grace_days)
        if datetime.utcnow() <= expiry_deadline:
            is_in_grace = True
            grace_expiry = expiry_deadline.isoformat()
            fine_amount, _ = calculate_fine_and_total(db, customer.id, reservation.amount or 1500.0, reservation.end_date)
        else:
            # Fully expired past grace period, treat as no reservation
            reservation = None
            
    if not reservation:
        return {"msg": "No active reservation found.", "customer_name": customer.name, "customer_status": customer.status}
        
    expires_at = None
    if reservation.status == "pending":
        hold_setting = db.query(DBSetting).filter(DBSetting.key == "seat_hold_duration_minutes").first()
        hold_duration = 15
        if hold_setting:
            try:
                hold_duration = int(hold_setting.value)
            except ValueError:
                pass
        expires_at = (reservation.created_at + timedelta(minutes=hold_duration)).isoformat()

    return {
        "customer_name": customer.name,
        "customer_status": customer.status,
        "customer_id": str(customer.id),
        "seat_number": reservation.seat_number,
        "subsection": reservation.subsection,
        "start_date": reservation.start_date,
        "end_date": reservation.end_date,
        "status": "grace" if is_in_grace else reservation.status,
        "amount": (reservation.amount or 1500.0) + fine_amount,
        "expires_at": expires_at,
        "grace_expiry": grace_expiry,
        "loyalty_tier": loyalty_tier,
        "grace_days": grace_days,
        "late_fine": fine_amount
    }

@router.get("/customers", response_model=PaginatedResponse[schemas.Customer])
def get_customers(
    page: int = 1, 
    size: int = 10, 
    search: str = "", 
    organization: Optional[str] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    db: Session = Depends(get_db), 
    user_payload: dict = Depends(RoleChecker(ALL_ROLES))
):
    query = db.query(schemas.DBCustomer)
    
    # 0. Enforce ability-based organization segregation
    user_role = user_payload.get("role")
    allowed_orgs = get_allowed_orgs(user_role, db)
    if "*" not in allowed_orgs:
        query = query.filter(schemas.DBCustomer.organization.in_(allowed_orgs))
    
    # 1. Filtering
    if organization and organization != "All Organizations":
        orgs = [o.strip() for o in organization.split(",") if o.strip()]
        if orgs:
            query = query.filter(schemas.DBCustomer.organization.in_(orgs))
    if search:
        query = query.filter(
            (schemas.DBCustomer.name.ilike(f"%{search}%")) |
            (schemas.DBCustomer.email.ilike(f"%{search}%")) |
            (schemas.DBCustomer.phone.ilike(f"%{search}%"))
        )
        
    # 2. Sorting
    sort_attr = getattr(schemas.DBCustomer, sort_by) if sort_by and hasattr(schemas.DBCustomer, sort_by) else schemas.DBCustomer.name
    if sort_order == "desc":
        query = query.order_by(sort_attr.desc())
    else:
        query = query.order_by(sort_attr.asc())

    return paginate(query, page, size)

@router.post("/customers", response_model=schemas.Customer)
def create_customer(customer: schemas.CustomerBase, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    cust_data = customer.dict()
    cust_data.pop("seat_number", None)
    cust_data.pop("plan_cost", None)
    db_customer = schemas.DBCustomer(**cust_data)
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@router.post("/register", response_model=schemas.Customer)
def public_register_customer(customer: schemas.CustomerBase, db: Session = Depends(get_db)):
    """Public endpoint for customer self-registration via QR or Link."""
    existing = db.query(schemas.DBCustomer).filter(schemas.DBCustomer.email == customer.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    cust_data = customer.dict()
    seat_number = cust_data.pop("seat_number", None)
    plan_cost = cust_data.pop("plan_cost", None)
    
    # Process profile photo if present
    if cust_data.get("profile_photo"):
        cust_data["profile_photo"] = upload_base64_to_supabase(cust_data["profile_photo"], "avatars")
        
    # Process documents if present
    if cust_data.get("documents"):
        uploaded_docs = []
        for doc in cust_data["documents"]:
            if doc:
                uploaded_docs.append(upload_base64_to_supabase(doc, "documents"))
        cust_data["documents"] = uploaded_docs
        
    # 1. Create DBUser with no password for customers
    db_user = DBUser(
        email=customer.email,
        hashed_password="", # Password-less for customers
        role="customer",
        full_name=customer.name
    )
    db.add(db_user)
    db.flush() # Get user ID
    
    # 2. Create DBCustomer
    cust_data["user_id"] = db_user.id
    db_customer = schemas.DBCustomer(**cust_data)
    db.add(db_customer)
    db.flush() # Get customer ID
    
    if seat_number:
        new_res = DBReservation(
            customer_id=db_customer.id,
            seat_number=seat_number,
            subsection=db_customer.sub_organization or "Premium Zone",
            organization=db_customer.organization or "Trisha Library",
            sub_organization=db_customer.sub_organization or "Premium Zone",
            start_date=datetime.utcnow(),
            end_date=datetime.utcnow() + timedelta(days=30),
            amount=plan_cost if plan_cost is not None else 1500.0,
            pay_via="UPI",
            status="pending",
            created_at=datetime.utcnow()
        )
        db.add(new_res)
        
    db.commit()
    db.refresh(db_customer)
    return db_customer

@router.put("/customers/{customer_id}/approve", response_model=schemas.Customer)
def approve_customer(customer_id: str, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    """Admin endpoint to approve a pending customer."""
    import uuid
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer UUID format")

    customer = db.query(schemas.DBCustomer).filter(schemas.DBCustomer.id == customer_uuid).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    customer.status = "active"
    db.commit()
    db.refresh(customer)
    return customer

@router.post("/customers/scan")
def biometric_scan(_=Depends(RoleChecker(ALL_ROLES))):
    return {"status": "success", "message": "Biometric verification complete."}

@router.put("/customers/{customer_id}", response_model=schemas.Customer)
def update_customer(
    customer_id: str,
    customer_update: schemas.CustomerBase,
    db: Session = Depends(get_db),
    _ = Depends(PermissionChecker("manage_customers"))
):
    import uuid
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer UUID format")

    db_customer = db.query(schemas.DBCustomer).filter(schemas.DBCustomer.id == customer_uuid).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # Update fields
    for key, value in customer_update.dict(exclude_unset=True).items():
        if key not in ["seat_number", "plan_cost", "id", "user_id"]:
            setattr(db_customer, key, value)
            
    # If email or name changes, also sync the DBUser!
    if db_customer.user_id:
        db_user = db.query(DBUser).filter(DBUser.id == db_customer.user_id).first()
        if db_user:
            db_user.email = db_customer.email
            db_user.full_name = db_customer.name
    
    db.commit()
    db.refresh(db_customer)
    return db_customer

@router.delete("/customers/{customer_id}")
def delete_customer(
    customer_id: str,
    db: Session = Depends(get_db),
    _ = Depends(PermissionChecker("dismiss_customer"))
):
    import uuid
    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer UUID format")

    db_customer = db.query(schemas.DBCustomer).filter(schemas.DBCustomer.id == customer_uuid).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    
    # 1. Delete associated bills
    from ..billing.model_bills import DBBill
    db.query(DBBill).filter(DBBill.customer_id == db_customer.id).delete()

    # 2. Delete associated reservations
    db.query(DBReservation).filter(DBReservation.customer_id == db_customer.id).delete()

    # 3. Delete associated notifications referencing this customer_id
    from ..notifications.model_notifications import DBNotification
    db.query(DBNotification).filter(DBNotification.customer_id == db_customer.id).delete()
    
    # 4. Store user ID reference
    user_id = db_customer.user_id
    
    # 5. Delete customer record itself
    db.delete(db_customer)
    db.flush()  # Push delete to DB transaction first
    
    # 6. Delete remaining user notification logs and credentials
    if user_id:
        db.query(DBNotification).filter(DBNotification.user_id == user_id).delete()
        db.query(DBUser).filter(DBUser.id == user_id).delete()
        
    db.commit()
    return {"msg": "Customer and associated user account successfully deleted."}

@router.post("/customers/{customer_id}/transfer")
def transfer_customer(
    customer_id: str,
    transfer_req: schemas.CustomerTransferRequest,
    db: Session = Depends(get_db),
    _ = Depends(PermissionChecker("manage_customers"))
):
    import uuid
    from ..billing.model_bills import DBBill
    from ..settings.model_settings import DBSetting
    from ..reservations.model_reservations import DBReservation
    from ..reservations.model_seats import DBSeat

    try:
        customer_uuid = uuid.UUID(customer_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid customer UUID format")

    db_customer = db.query(schemas.DBCustomer).filter(schemas.DBCustomer.id == customer_uuid).first()
    if not db_customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    # 1. Update customer organization details
    db_customer.organization = transfer_req.new_organization
    db_customer.sub_organization = transfer_req.new_sub_organization
    
    # 2. Release their current seat holds
    if db_customer.seat_number:
        db.query(DBSeat).filter(DBSeat.seat_number == db_customer.seat_number).update({
            "status": "available",
            "held_by_customer_id": None,
            "held_by_customer_name": None,
            "hold_expires_at": None
        })
        db_customer.seat_number = None

    # 3. Expire current active reservations
    db.query(DBReservation).filter(
        DBReservation.customer_id == str(customer_uuid),
        DBReservation.status == "active"
    ).update({"status": "expired"})
    
    # 4. Generate transfer fee bill if configured
    fee_setting = db.query(DBSetting).filter(DBSetting.key == "customer_transfer_fee").first()
    transfer_fee = 0.0
    if fee_setting:
        try:
            transfer_fee = float(fee_setting.value)
        except ValueError:
            pass
            
    if transfer_fee > 0:
        new_bill = DBBill(
            customer_id=customer_uuid,
            amount=transfer_fee,
            status="pending",
            due_date=datetime.utcnow() + timedelta(days=7),
            description=f"Branch Transfer Fee ({transfer_req.new_organization})"
        )
        db.add(new_bill)
        
    db.commit()
    
    return {"msg": f"Customer transferred to {transfer_req.new_organization}. Please assign a new seat.", "fee_charged": transfer_fee > 0}
