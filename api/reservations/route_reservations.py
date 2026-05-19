from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_reservations as schemas
from ..customers.model_customers import DBCustomer
from ..auth_user.dependencies import RoleChecker, PermissionChecker, get_allowed_orgs
from typing import List, Optional
import uuid

router = APIRouter(prefix="/api", tags=["reservations"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff"]

from ..pagination import PaginatedResponse

def generate_sequential_seat_number(db: Session, organization: Optional[str], sub_organization: Optional[str]) -> str:
    # 1. Determine standard abbreviations
    org_prefix = ""
    sub_prefix = ""
    
    if organization and organization.strip():
        # Acronym logic: e.g. "Trisha Library" -> "TL"
        words = [w.strip() for w in organization.replace("-", " ").replace("_", " ").split() if w.strip()]
        if len(words) > 1:
            org_prefix = "".join([w[0].upper() for w in words if w[0].isalnum()])
        else:
            org_prefix = words[0][:3].upper() if words else "ORG"
    
    if sub_organization and sub_organization.strip():
        words = [w.strip() for w in sub_organization.replace("-", " ").replace("_", " ").split() if w.strip()]
        if len(words) > 1:
            sub_prefix = "".join([w[0].upper() for w in words if w[0].isalnum()])
        else:
            sub_prefix = words[0][:3].upper() if words else "SUB"
            
    # 2. Formulate prefix
    prefix = ""
    if org_prefix and sub_prefix:
        prefix = f"{org_prefix}-{sub_prefix}-"
    elif org_prefix:
        prefix = f"{org_prefix}-"
    elif sub_prefix:
        prefix = f"{sub_prefix}-"
    else:
        prefix = "S-"
        
    # 3. Query all seat numbers starting with prefix to find the next sequential number
    existing_seats = db.query(schemas.DBReservation.seat_number).filter(
        schemas.DBReservation.seat_number.like(f"{prefix}%")
    ).all()
    
    max_num = 0
    for row in existing_seats:
        seat_num = row[0]
        suffix = seat_num[len(prefix):]
        try:
            val = int(suffix)
            if val > max_num:
                max_num = val
        except ValueError:
            pass
            
    next_num = max_num + 1
    return f"{prefix}{next_num:03d}"

@router.get("/reservations/next-seat")
def get_next_seat(
    organization: Optional[str] = None,
    sub_organization: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker("manage_reservations"))
):
    seat_num = generate_sequential_seat_number(db, organization, sub_organization)
    return {"seat_number": seat_num}

@router.get("/reservations", response_model=PaginatedResponse[schemas.ReservationWithCustomer])
def get_reservations(
    page: int = 1, 
    size: int = 10, 
    search: Optional[str] = None,
    status: Optional[str] = None,
    organization: Optional[str] = None,
    customer_id: Optional[str] = None,
    sort_by: Optional[str] = "start_date",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db), 
    user_payload: dict = Depends(PermissionChecker("manage_reservations"))
):

    query = db.query(schemas.DBReservation, DBCustomer.name).join(DBCustomer)
    
    # 0. Enforce ability-based organization segregation
    user_role = user_payload.get("role")
    allowed_orgs = get_allowed_orgs(user_role, db)
    if "*" not in allowed_orgs:
        query = query.filter(schemas.DBReservation.organization.in_(allowed_orgs))
    
    # 1. Filtering
    if status:
        query = query.filter(schemas.DBReservation.status == status)
    if organization and organization != "All Organizations":
        orgs = [o.strip() for o in organization.split(",") if o.strip()]
        if orgs:
            query = query.filter(schemas.DBReservation.organization.in_(orgs))
    if customer_id:
        try:
            cust_uuid = uuid.UUID(customer_id)
            query = query.filter(schemas.DBReservation.customer_id == cust_uuid)
        except ValueError:
            pass
    if search:
        query = query.filter(
            (DBCustomer.name.ilike(f"%{search}%")) |
            (schemas.DBReservation.seat_number.ilike(f"%{search}%")) |
            (schemas.DBReservation.subsection.ilike(f"%{search}%"))
        )
        
    # 2. Sorting
    sort_attr = getattr(schemas.DBReservation, sort_by) if sort_by and hasattr(schemas.DBReservation, sort_by) else schemas.DBReservation.start_date
    if sort_order == "desc":
        query = query.order_by(sort_attr.desc())
    else:
        query = query.order_by(sort_attr.asc())

    total = query.count()
    pages = (total + size - 1) // size if size > 0 else 0
    if size > 0:
        results = query.offset((page - 1) * size).limit(size).all()
    else:
        results = query.all()
    items = []
    for row in results:
        res, cust_name = row
        items.append(schemas.ReservationWithCustomer(
            **res.__dict__,
            customer_name=cust_name
        ))
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

@router.post("/reservations")
def create_reservation(res: schemas.ReservationBase, db: Session = Depends(get_db), _=Depends(PermissionChecker("manage_reservations"))):
    res_dict = res.dict()
    
    # Unification of subsection and sub_organization
    if res_dict.get("sub_organization") and not res_dict.get("subsection"):
        res_dict["subsection"] = res_dict["sub_organization"]
    elif res_dict.get("subsection") and not res_dict.get("sub_organization"):
        res_dict["sub_organization"] = res_dict["subsection"]
        
    # Auto-generate seat number if blank or 'auto'
    if not res_dict.get("seat_number") or res_dict["seat_number"] == "auto":
        res_dict["seat_number"] = generate_sequential_seat_number(db, res_dict.get("organization"), res_dict.get("sub_organization"))
        
    db_res = schemas.DBReservation(**res_dict)
    db.add(db_res)
    db.commit()
    db.refresh(db_res)
    return db_res

@router.patch("/reservations/{res_id}/status")
def update_reservation_status(res_id: uuid.UUID, update: schemas.ReservationStatusUpdate, db: Session = Depends(get_db), _=Depends(PermissionChecker("manage_reservations"))):

    db_res = db.query(schemas.DBReservation).filter(schemas.DBReservation.id == res_id).first()
    if not db_res:
        raise HTTPException(status_code=404, detail="Reservation not found")
    db_res.status = update.status
    db.commit()
    return {"status": "updated"}

from pydantic import BaseModel
from datetime import datetime, timedelta

class SeatOccupyRequest(BaseModel):
    seat_number: str
    organization: str
    sub_organization: str
    plan_cost: float

@router.post("/reservations/occupy")
def occupy_seat(
    req: SeatOccupyRequest, 
    db: Session = Depends(get_db), 
    user_payload: dict = Depends(RoleChecker(["customer", "admin", "manager"]))
):
    """
    Lets a logged-in customer hold/occupy an available seat before payment.
    Enforces that they don't double-book, that they don't double-occupy, and that the seat is vacant.
    Also protects loyal customer grace periods from collision.
    """
    from .route_seats import cleanup_expired_holds
    from ..billing.model_bills import DBBill
    from ..billing.model_plans import DBPlan
    from .loyalty import calculate_loyalty_and_grace
    
    # 1. Dynamic cleanup
    cleanup_expired_holds(db)

    # 2. Fetch customer profile
    user_email = user_payload.get("sub")
    customer = db.query(DBCustomer).filter(DBCustomer.email == user_email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer profile not found.")

    # 3. Check for existing active/pending holds (Double Occupying Protection)
    existing = db.query(schemas.DBReservation).filter(
        schemas.DBReservation.customer_id == customer.id,
        schemas.DBReservation.status.in_(["paid", "pending"])
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="You already have an active or pending reservation. Please complete payment or let it expire."
        )

    # 4. Plan Cost / Price Tampering validation
    plan = db.query(DBPlan).filter(DBPlan.cost == int(req.plan_cost)).first()
    if not plan:
        raise HTTPException(
            status_code=400,
            detail="Invalid subscription plan cost. Price tampering detected."
        )

    # 5. Check if another customer's late renewal grace lock is active on this seat
    grace_res = db.query(schemas.DBReservation).filter(
        schemas.DBReservation.seat_number == req.seat_number,
        schemas.DBReservation.organization == req.organization,
        schemas.DBReservation.sub_organization == req.sub_organization,
        schemas.DBReservation.status == "paid"
    ).order_by(schemas.DBReservation.end_date.desc()).first()

    if grace_res and grace_res.end_date and grace_res.end_date < datetime.utcnow():
        tier, grace_days = calculate_loyalty_and_grace(db, grace_res.customer_id)
        expiry_deadline = grace_res.end_date + timedelta(days=grace_days)
        if datetime.utcnow() <= expiry_deadline:
            raise HTTPException(
                status_code=400,
                detail=f"Seat {req.seat_number} is locked under active late renewal protection for a loyal member."
            )

    # 6. Check if the target seat is already held or paid (Double Booking Protection)
    active_seat = db.query(schemas.DBReservation).filter(
        schemas.DBReservation.seat_number == req.seat_number,
        schemas.DBReservation.organization == req.organization,
        schemas.DBReservation.sub_organization == req.sub_organization,
        schemas.DBReservation.status.in_(["paid", "pending"])
    ).first()

    if active_seat:
        raise HTTPException(
            status_code=400,
            detail=f"Seat {req.seat_number} is already occupied or held by another user."
        )

    # 7. Create pending reservation hold
    new_res = schemas.DBReservation(
        customer_id=customer.id,
        seat_number=req.seat_number,
        subsection=req.sub_organization,
        organization=req.organization,
        sub_organization=req.sub_organization,
        start_date=datetime.utcnow(),
        end_date=datetime.utcnow() + timedelta(days=30),
        amount=req.plan_cost,
        pay_via="UPI",
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(new_res)
    db.flush()

    # 8. Create a pending bill matching this hold
    new_bill = DBBill(
        customer_id=customer.id,
        amount=req.plan_cost,
        status="pending",
        pay_via="UPI",
        due_date=datetime.utcnow(),
        month_ending=datetime.utcnow() + timedelta(days=30)
    )
    db.add(new_bill)
    db.commit()

    return {"message": "Seat successfully held. Please complete payment within the hold period.", "reservation_id": str(new_res.id)}

class DismissCustomerRequest(BaseModel):
    reason: str

@router.post("/admin/customers/{customer_id}/dismiss")
def dismiss_customer(
    customer_id: uuid.UUID,
    req: DismissCustomerRequest,
    db: Session = Depends(get_db),
    _ = Depends(PermissionChecker("dismiss_customer"))
):
    """
    Administrative Eviction Endpoint:
    Allows admins or managers to evict/dismiss a customer from a paid/held seat.
    Immediately vacates the seat, cancels active reservations & pending bills,
    and logs/alerts the user with a custom reason.
    """
    customer = db.query(DBCustomer).filter(DBCustomer.id == customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
        
    active_reservations = db.query(schemas.DBReservation).filter(
        schemas.DBReservation.customer_id == customer_id,
        schemas.DBReservation.status.in_(["paid", "pending"])
    ).all()
    
    if not active_reservations:
        raise HTTPException(status_code=400, detail="Customer does not currently occupy any active/pending seat")
        
    cancelled_seats = []
    for res in active_reservations:
        res.status = "cancelled"
        cancelled_seats.append(res.seat_number)
        
    from ..billing.model_bills import DBBill
    pending_bills = db.query(DBBill).filter(
        DBBill.customer_id == customer_id,
        DBBill.status == "pending"
    ).all()
    for bill in pending_bills:
        bill.status = "cancelled"
        
    from ..notifications.model_notifications import DBNotification
    notif = DBNotification(
        customer_id=customer_id,
        message=f"Administrative Notice: Your seat occupancy has been dismissed/released. Reason: {req.reason}.",
        sent_at=datetime.utcnow(),
        is_read=False
    )
    db.add(notif)
    db.commit()
    
    return {
        "status": "success",
        "message": f"Customer {customer.email} evicted successfully",
        "cancelled_seats": cancelled_seats
    }
