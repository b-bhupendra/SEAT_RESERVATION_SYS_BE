from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_bills as schemas
from ..customers.model_customers import DBCustomer
from ..auth_user.dependencies import RoleChecker
from typing import List
import uuid

router = APIRouter(prefix="/api", tags=["billing"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff"]

from ..pagination import PaginatedResponse

@router.get("/bills", response_model=PaginatedResponse[schemas.Bill])
def get_bills(
    page: int = 1, 
    size: int = 10, 
    search: Optional[str] = None,
    status: Optional[str] = None,
    sort_by: Optional[str] = "due_date",
    sort_order: Optional[str] = "desc",
    db: Session = Depends(get_db), 
    _=Depends(RoleChecker(ALL_ROLES))
):
    query = db.query(schemas.DBBill, DBCustomer.name, DBCustomer.phone).join(DBCustomer)
    
    # 1. Filtering
    if status:
        query = query.filter(schemas.DBBill.status == status)
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
def create_bill(bill: schemas.BillCreate, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
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
def update_bill_status(bill_id: uuid.UUID, update: schemas.BillStatusUpdate, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    db_bill = db.query(schemas.DBBill).filter(schemas.DBBill.id == bill_id).first()
    if not db_bill:
        raise HTTPException(status_code=404, detail="Bill not found")
    db_bill.status = update.status
    db.commit()
    return {"status": "updated"}
