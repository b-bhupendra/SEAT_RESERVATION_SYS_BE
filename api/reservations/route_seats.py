from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Optional
import uuid

from ..db_core import get_db
from .model_seats import DBSeat, Seat, SeatGenerateRequest
from .model_reservations import DBReservation
from ..customers.model_customers import DBCustomer
from ..settings.model_settings import DBSetting
from ..auth_user.dependencies import RoleChecker

router = APIRouter(prefix="/api", tags=["seats"])

ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff", "customer"]

def cleanup_expired_holds(db: Session):
    """
    Looks up any pending reservation seat holds and releases/cancels them
    if they exceed the configured hold time period limit.
    """
    # Fetch the hold duration setting (default 15 minutes)
    hold_setting = db.query(DBSetting).filter(DBSetting.key == "seat_hold_duration_minutes").first()
    hold_duration = 15
    if hold_setting:
        try:
            hold_duration = int(hold_setting.value)
        except ValueError:
            pass

    cutoff = datetime.utcnow() - timedelta(minutes=hold_duration)
    
    # Fetch pending reservations that are older than the cutoff
    expired_holds = db.query(DBReservation).filter(
        DBReservation.status == "pending",
        DBReservation.created_at < cutoff
    ).all()

    for hold in expired_holds:
        hold.status = "cancelled"
        print(f"DEBUG: Automatically released expired seat hold for seat {hold.seat_number} (Customer ID: {hold.customer_id})")

    if expired_holds:
        db.commit()

@router.get("/seats", response_model=List[Seat])
def get_seats(
    organization: Optional[str] = None,
    sub_organization: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Returns list of seats along with their dynamic real-time status.
    Cleans up expired holds before calculation.
    """
    # Run dynamic expiration check first
    cleanup_expired_holds(db)

    # Fetch hold duration setting for expires_at calculation
    hold_setting = db.query(DBSetting).filter(DBSetting.key == "seat_hold_duration_minutes").first()
    hold_duration = 15
    if hold_setting:
        try:
            hold_duration = int(hold_setting.value)
        except ValueError:
            pass

    # Query all seats
    query = db.query(DBSeat)
    if organization and organization != "All Organizations":
        orgs = [o.strip() for o in organization.split(",") if o.strip()]
        if orgs:
            query = query.filter(DBSeat.organization.in_(orgs))
    if sub_organization and sub_organization != "All Sub-organizations":
        query = query.filter(DBSeat.sub_organization == sub_organization)
    
    seats = query.all()

    results = []
    for seat in seats:
        # Check active reservations for this seat
        # Status can be paid or pending
        latest_res = db.query(DBReservation, DBCustomer.name).join(
            DBCustomer, DBReservation.customer_id == DBCustomer.id
        ).filter(
            DBReservation.seat_number == seat.seat_number,
            DBReservation.organization == seat.organization,
            DBReservation.sub_organization == seat.sub_organization,
            DBReservation.status.in_(["paid", "pending"])
        ).order_by(DBReservation.created_at.desc()).first()

        status = "available"
        held_by_customer_id = None
        held_by_customer_name = None
        expires_at = None

        if latest_res:
            res, cust_name = latest_res
            if res.status == "paid":
                # Double check expiration (if paid, occupies until end_date)
                if not res.end_date or res.end_date > datetime.utcnow():
                    status = "paid"
            elif res.status == "pending":
                # This is a pending hold
                status = "held"
                held_by_customer_id = res.customer_id
                held_by_customer_name = cust_name
                expire_time = res.created_at + timedelta(minutes=hold_duration)
                expires_at = expire_time.isoformat()

        results.append(Seat(
            id=seat.id,
            seat_number=seat.seat_number,
            organization=seat.organization,
            sub_organization=seat.sub_organization,
            status=status,
            held_by_customer_id=held_by_customer_id,
            held_by_customer_name=held_by_customer_name,
            expires_at=expires_at
        ))

    return results

@router.post("/seats/generate", status_code=status.HTTP_201_CREATED)
def generate_seats(
    req: SeatGenerateRequest,
    db: Session = Depends(get_db),
    _=Depends(RoleChecker(ADMIN_MGR))
):
    """
    Bulk generates list of seats for an organization and sub-organization.
    """
    prefix = req.prefix.strip()
    if not prefix:
        prefix = "S-"
    elif not prefix.endswith("-") and not prefix.endswith("_"):
        prefix = f"{prefix}-"

    # Find the next sequential number by looking up existing seat numbers with prefix
    existing_seats = db.query(DBSeat.seat_number).filter(
        DBSeat.organization == req.organization,
        DBSeat.sub_organization == req.sub_organization,
        DBSeat.seat_number.like(f"{prefix}%")
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

    created_seats = []
    for i in range(1, req.count + 1):
        num = max_num + i
        seat_number = f"{prefix}{num:03d}"
        
        # Verify duplicate seat
        exists = db.query(DBSeat).filter(
            DBSeat.organization == req.organization,
            DBSeat.sub_organization == req.sub_organization,
            DBSeat.seat_number == seat_number
        ).first()

        if not exists:
            new_seat = DBSeat(
                seat_number=seat_number,
                organization=req.organization,
                sub_organization=req.sub_organization
            )
            db.add(new_seat)
            created_seats.append(new_seat)

    if created_seats:
        db.commit()

    return {"message": f"Successfully generated {len(created_seats)} seats.", "count": len(created_seats)}

@router.post("/seats/cleanup")
def trigger_cleanup(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Cron endpoint to periodically clean up expired seat holds.
    Can be protected by a CRON_SECRET token injected by Vercel.
    """
    import os
    cron_secret = os.getenv("CRON_SECRET")
    if cron_secret and authorization != f"Bearer {cron_secret}":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized cron invocation"
        )
        
    cleanup_expired_holds(db)
    return {"status": "success", "message": "Expired holds cleaned up successfully."}
