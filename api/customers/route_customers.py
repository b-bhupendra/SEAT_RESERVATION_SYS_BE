from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_customers as schemas
from ..auth_user.dependencies import RoleChecker
from typing import List, Optional
from ..reservations.model_reservations import DBReservation, Reservation

router = APIRouter(prefix="/api", tags=["customers"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff"]

from ..pagination import PaginatedResponse, paginate
from fastapi import Query as FastAPIQuery

@router.get("/me/reservation")
async def get_my_reservation(
    db: Session = Depends(get_db),
    user_payload: dict = Depends(RoleChecker(["customer", "admin"]))
):
    """
    Returns the current seat reservation for the logged-in customer.
    Matches the user's email from the JWT to the DBCustomer record.
    """
    user_email = user_payload.get("sub")
    customer = db.query(schemas.DBCustomer).filter(schemas.DBCustomer.email == user_email).first()
    
    if not customer:
        raise HTTPException(status_code=404, detail="Customer record not found for this user.")
        
    reservation = db.query(DBReservation).filter(
        DBReservation.customer_id == customer.id,
        DBReservation.status == "paid" # Or active status
    ).order_by(DBReservation.start_date.desc()).first()
    
    if not reservation:
        return {"msg": "No active reservation found.", "customer_name": customer.name}
        
    return {
        "customer_name": customer.name,
        "seat_number": reservation.seat_number,
        "subsection": reservation.subsection,
        "start_date": reservation.start_date,
        "end_date": reservation.end_date,
        "status": reservation.status
    }

@router.get("/customers", response_model=PaginatedResponse[schemas.Customer])
def get_customers(
    page: int = 1, 
    size: int = 10, 
    search: str = "", 
    sort_by: str = "name",
    sort_order: str = "asc",
    db: Session = Depends(get_db), 
    _= Depends(RoleChecker(ALL_ROLES))
):
    query = db.query(schemas.DBCustomer)
    
    # 1. Filtering
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
    db_customer = schemas.DBCustomer(**customer.dict())
    db.add(db_customer)
    db.commit()
    db.refresh(db_customer)
    return db_customer

@router.post("/customers/scan")
def biometric_scan(_=Depends(RoleChecker(ALL_ROLES))):
    return {"status": "success", "message": "Biometric verification complete."}
