from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_reservations as schemas
from ..customers.model_customers import DBCustomer
from ..auth_user.dependencies import RoleChecker
from typing import List
import uuid

router = APIRouter(prefix="/api", tags=["reservations"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff"]

from ..pagination import PaginatedResponse

@router.get("/reservations", response_model=PaginatedResponse[schemas.ReservationWithCustomer])
def get_reservations(
    page: int = 1, 
    size: int = 10, 
    search: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: Optional[str] = "start_date",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db), 
    _=Depends(RoleChecker(ALL_ROLES))
):
    query = db.query(schemas.DBReservation, DBCustomer.name).join(DBCustomer)
    
    # 1. Filtering
    if status:
        query = query.filter(schemas.DBReservation.status == status)
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
def create_reservation(res: schemas.ReservationBase, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    db_res = schemas.DBReservation(**res.dict())
    db.add(db_res)
    db.commit()
    db.refresh(db_res)
    return db_res

@router.patch("/reservations/{res_id}/status")
def update_reservation_status(res_id: uuid.UUID, update: schemas.ReservationStatusUpdate, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    db_res = db.query(schemas.DBReservation).filter(schemas.DBReservation.id == res_id).first()
    if not db_res:
        raise HTTPException(status_code=404, detail="Reservation not found")
    db_res.status = update.status
    db.commit()
    return {"status": "updated"}
