from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_bills as schemas
from ..customers.model_customers import DBCustomer
from ..auth_user.dependencies import RoleChecker, PermissionChecker, get_allowed_orgs
from typing import List, Optional
import uuid
from datetime import datetime, timedelta

router = APIRouter(prefix="/api", tags=["billing"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES  = ["admin", "manager", "staff"]

from ..pagination import PaginatedResponse

@router.get("/bills", response_model=PaginatedResponse[schemas.Bill])
def get_bills(
    page: int = 1, 
    size: int = 10, 
    search: Optional[str] = None,
    customer_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    organization: Optional[str] = None,
    sort_by: Optional[str] = "due_date",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db), 
    user_payload: dict = Depends(PermissionChecker("view_billing"))
):

    query = db.query(schemas.DBBill, DBCustomer.name, DBCustomer.phone).join(DBCustomer)
    
    # 0. Enforce ability-based organization segregation
    user_role = user_payload.get("role")
    allowed_orgs = get_allowed_orgs(user_role, db)
    if "*" not in allowed_orgs:
        query = query.filter(DBCustomer.organization.in_(allowed_orgs))
    
    # 1. Filtering
    if customer_id:
        query = query.filter(schemas.DBBill.customer_id == customer_id)
    if status:
        query = query.filter(schemas.DBBill.status == status)
    if organization and organization != "All Organizations":
        orgs = [o.strip() for o in organization.split(",") if o.strip()]
        if orgs:
            query = query.filter(DBCustomer.organization.in_(orgs))
    if search:
        query = query.filter(DBCustomer.name.ilike(f"%{search}%"))
        
    # 2. Sorting
    sort_attr = getattr(schemas.DBBill, sort_by) if sort_by and hasattr(schemas.DBBill, sort_by) else schemas.DBBill.due_date
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
        bill, cust_name, cust_phone = row
        items.append(schemas.Bill(
            **bill.__dict__,
            customer_name=cust_name,
            customer_phone=cust_phone
        ))
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

@router.post("/bills", response_model=schemas.Bill)
def create_bill(bill: schemas.BillCreate, db: Session = Depends(get_db), _=Depends(PermissionChecker("manage_billing"))):
    db_bill = schemas.DBBill(**bill.dict())
    db.add(db_bill)
    db.commit()
    db.refresh(db_bill)
    customer = db.query(DBCustomer).filter(DBCustomer.id == db_bill.customer_id).first()
    return schemas.Bill(
        **db_bill.__dict__, 
        customer_name=customer.name if customer else None, 
        customer_phone=customer.phone if customer else None
    )

@router.patch("/bills/{bill_id}/status")
def update_bill_status(bill_id: uuid.UUID, update: schemas.BillStatusUpdate, db: Session = Depends(get_db), _=Depends(PermissionChecker("manage_billing"))):

    db_bill = db.query(schemas.DBBill).filter(schemas.DBBill.id == bill_id).first()
    if not db_bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    db_bill.status = update.status
    db.commit()
    return {"status": "updated"}

# ── CASH PAYMENT PARALLEL SYSTEM ─────────────────────────────────────────────

def _get_loyalty_cash_hours(customer_id: uuid.UUID, db: Session) -> int:
    """
    Returns the cash payment window in hours for a customer based on their loyalty tier.
    Reads tier-specific settings, falling back to the global default.
    """
    from ..settings.model_settings import DBSetting
    from ..reservations.loyalty import calculate_loyalty_and_grace

    paid_bills = db.query(schemas.DBBill).filter(
        schemas.DBBill.customer_id == customer_id,
        schemas.DBBill.status == "paid"
    ).count()

    loyalty = calculate_loyalty_and_grace(paid_bills, db)
    tier = loyalty.get("tier", "bronze").lower()

    key_map = {
        "bronze": "cash_payment_bronze_hours",
        "silver": "cash_payment_silver_hours",
        "gold":   "cash_payment_gold_hours",
    }
    key = key_map.get(tier, "cash_payment_window_hours")
    setting = db.query(DBSetting).filter(DBSetting.key == key).first()
    if setting:
        try:
            return int(setting.value)
        except ValueError:
            pass
    # global fallback
    fallback = db.query(DBSetting).filter(DBSetting.key == "cash_payment_window_hours").first()
    return int(fallback.value) if fallback else 48


@router.post("/bills/cash-request", response_model=schemas.Bill)
def request_cash_payment(
    req: schemas.CashPaymentRequest,
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(ALL_ROLES))
):
    """
    Customer or staff registers a cash payment intent.
    Creates a Bill (status=cash_pending) and a pending Reservation hold.
    The seat is held with status 'cash_pending' until admin approves.
    """
    from ..reservations.model_reservations import DBReservation
    from ..notifications.model_notifications import DBNotification

    customer = db.query(DBCustomer).filter(DBCustomer.id == req.customer_id).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    # Prevent duplicate pending cash requests for the same customer
    existing = db.query(schemas.DBBill).filter(
        schemas.DBBill.customer_id == req.customer_id,
        schemas.DBBill.status == "cash_pending"
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Customer already has a pending cash payment request.")

    now = datetime.utcnow()
    # Bill stays open until approved (due_date = now + global window as placeholder)
    hours = _get_loyalty_cash_hours(req.customer_id, db)
    provisional_due = now + timedelta(hours=hours)

    bill = schemas.DBBill(
        customer_id=req.customer_id,
        amount=req.amount,
        due_date=provisional_due,
        month_ending=now + timedelta(days=30),
        pay_via="Cash",
        status="cash_pending",
        notes=req.notes or "Cash payment requested by customer."
    )
    db.add(bill)
    db.flush()

    # Create pending reservation hold for the seat
    reservation = DBReservation(
        customer_id=req.customer_id,
        subsection=req.sub_organization,
        seat_number=req.seat_number,
        organization=req.organization,
        sub_organization=req.sub_organization,
        start_date=now,
        end_date=now + timedelta(days=30),
        amount=req.amount,
        pay_via="Cash",
        status="pending"
    )
    db.add(reservation)

    # Notify admin
    db.add(DBNotification(
        customer_id=req.customer_id,
        message=(
            f"Cash payment request submitted for seat {req.seat_number} "
            f"({req.organization} / {req.sub_organization}). "
            f"Amount: ₹{req.amount}. Awaiting admin approval. "
            f"Customer note: {req.notes or 'None'}"
        )
    ))
    db.commit()
    db.refresh(bill)

    return schemas.Bill(
        **bill.__dict__,
        customer_name=customer.name,
        customer_phone=customer.phone
    )


@router.post("/bills/{bill_id}/cash-approve")
def approve_cash_payment(
    bill_id: uuid.UUID,
    req: schemas.CashApproveRequest,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker("approve_cash_payment"))
):
    """
    Staff/admin approves the cash payment request.
    Sets an explicit cash_due_date deadline (N hours from now) by the ability holder.
    Customer must physically deliver cash before this deadline.
    """
    from ..notifications.model_notifications import DBNotification

    bill = db.query(schemas.DBBill).filter(schemas.DBBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.status != "cash_pending":
        raise HTTPException(status_code=400, detail=f"Bill is not in cash_pending state (current: {bill.status}).")

    if req.cash_due_hours <= 0 or req.cash_due_hours > 720:
        raise HTTPException(status_code=400, detail="Cash window must be between 1 and 720 hours (30 days).")

    now = datetime.utcnow()
    deadline = now + timedelta(hours=req.cash_due_hours)
    bill.status = "cash_approved"
    bill.cash_due_date = deadline
    bill.due_date = deadline
    bill.notes = req.notes or bill.notes

    customer = db.query(DBCustomer).filter(DBCustomer.id == bill.customer_id).first()

    db.add(DBNotification(
        customer_id=bill.customer_id,
        message=(
            f"✅ Your cash payment request has been approved! "
            f"Please deliver ₹{bill.amount} by "
            f"{deadline.strftime('%d %b %Y, %I:%M %p')} UTC. "
            f"Admin note: {req.notes or 'Bring to front desk.'} "
            f"Your seat is reserved until the deadline."
        )
    ))
    db.commit()

    return {
        "status": "approved",
        "cash_due_date": deadline.isoformat(),
        "message": f"Cash payment window set: {req.cash_due_hours}h (until {deadline.strftime('%d %b %Y %H:%M')} UTC)."
    }


@router.post("/bills/{bill_id}/cash-confirm")
def confirm_cash_received(
    bill_id: uuid.UUID,
    req: schemas.CashConfirmRequest,
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker("approve_cash_payment"))
):
    """
    Staff confirms physical cash has been received.
    Finalizes the bill (status=paid) and activates the reservation.
    """
    from ..reservations.model_reservations import DBReservation
    from ..notifications.model_notifications import DBNotification

    bill = db.query(schemas.DBBill).filter(schemas.DBBill.id == bill_id).first()
    if not bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    if bill.status not in ("cash_approved", "cash_pending"):
        raise HTTPException(status_code=400, detail=f"Bill cannot be confirmed (current status: {bill.status}).")

    now = datetime.utcnow()
    bill.status = "paid"
    bill.pay_date = now
    bill.notes = (bill.notes or "") + f" | Confirmed: {req.notes or 'Cash received.'}"

    # Activate the linked pending reservation
    reservation = db.query(DBReservation).filter(
        DBReservation.customer_id == bill.customer_id,
        DBReservation.status == "pending"
    ).order_by(DBReservation.created_at.desc()).first()

    if reservation:
        reservation.status = "paid"
        reservation.start_date = now
        reservation.end_date = now + timedelta(days=30)
        reservation.pay_via = "Cash"

    db.add(DBNotification(
        customer_id=bill.customer_id,
        message=(
            f"🎉 Cash payment of ₹{bill.amount} confirmed! "
            f"Your seat is now fully active for 30 days. "
            f"Note: {req.notes or 'Cash received successfully.'}"
        )
    ))
    db.commit()

    return {
        "status": "paid",
        "message": "Cash payment confirmed. Seat is now fully activated.",
        "reservation_status": reservation.status if reservation else "no linked reservation found"
    }


@router.post("/bills/cash-expire")
def expire_overdue_cash_requests(
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker("approve_cash_payment"))
):
    """
    Manually or scheduled: expire all cash_approved bills that exceeded their deadline.
    Releases the associated seat reservation back to public.
    """
    from ..reservations.model_reservations import DBReservation
    from ..notifications.model_notifications import DBNotification

    now = datetime.utcnow()
    overdue_bills = db.query(schemas.DBBill).filter(
        schemas.DBBill.status.in_(["cash_pending", "cash_approved"]),
        schemas.DBBill.cash_due_date != None,
        schemas.DBBill.cash_due_date < now
    ).all()

    expired = []
    for bill in overdue_bills:
        bill.status = "expired"
        customer = db.query(DBCustomer).filter(DBCustomer.id == bill.customer_id).first()

        # Release linked pending reservation
        reservation = db.query(DBReservation).filter(
            DBReservation.customer_id == bill.customer_id,
            DBReservation.status == "pending"
        ).order_by(DBReservation.created_at.desc()).first()
        if reservation:
            reservation.status = "cancelled"

        db.add(DBNotification(
            customer_id=bill.customer_id,
            message=(
                f"⚠️ Your cash payment window has expired. "
                f"Seat {reservation.seat_number if reservation else 'N/A'} has been released. "
                f"Please contact reception or re-apply for a new seat."
            )
        ))
        expired.append(str(bill.id))

    db.commit()
    return {"expired_count": len(expired), "expired_bill_ids": expired}


@router.get("/bills/cash-pending")
def list_cash_pending_bills(
    db: Session = Depends(get_db),
    _=Depends(PermissionChecker("approve_cash_payment"))
):
    """
    Returns all bills awaiting cash payment approval or confirmation.
    """
    bills = db.query(schemas.DBBill, DBCustomer.name, DBCustomer.phone).join(
        DBCustomer, schemas.DBBill.customer_id == DBCustomer.id
    ).filter(
        schemas.DBBill.status.in_(["cash_pending", "cash_approved"])
    ).order_by(schemas.DBBill.due_date.asc()).all()

    return [
        {
            "id": str(bill.id),
            "customer_id": str(bill.customer_id),
            "customer_name": name,
            "customer_phone": phone,
            "amount": bill.amount,
            "status": bill.status,
            "cash_due_date": bill.cash_due_date.isoformat() if bill.cash_due_date else None,
            "due_date": bill.due_date.isoformat() if bill.due_date else None,
            "notes": bill.notes,
            "pay_via": bill.pay_via,
        }
        for bill, name, phone in bills
    ]

@router.get("/me/bills", response_model=List[schemas.Bill])
def get_my_bills(
    db: Session = Depends(get_db),
    current_user = Depends(PermissionChecker("view_portal"))
):
    """
    Retrieves the logged-in customer's billing list.
    """
    user_email = current_user.get("sub")
    customer = db.query(DBCustomer).filter(DBCustomer.email == user_email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Customer record not found for this user.")
        
    bills = db.query(schemas.DBBill, DBCustomer.name, DBCustomer.phone).join(
        DBCustomer, schemas.DBBill.customer_id == DBCustomer.id
    ).filter(
        schemas.DBBill.customer_id == customer.id
    ).order_by(schemas.DBBill.due_date.desc()).all()
    
    items = []
    for row in bills:
        bill, name, phone = row
        items.append(schemas.Bill(
            **bill.__dict__,
            customer_name=name,
            customer_phone=phone
        ))
    return items

