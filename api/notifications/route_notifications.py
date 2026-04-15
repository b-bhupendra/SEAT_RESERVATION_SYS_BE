from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_notifications as schemas
from ..customers.model_customers import DBCustomer
from ..auth_user.dependencies import RoleChecker
from typing import List
import uuid

router = APIRouter(prefix="/api", tags=["notifications"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff"]

from ..pagination import PaginatedResponse
from ..supabase_utils import notify_supabase

@router.post("/notifications")
def create_notification(notification: schemas.NotificationBase, db: Session = Depends(get_db), _=Depends(RoleChecker(ADMIN_MGR))):
    # 1. Save to SQL DB for history
    db_notif = schemas.DBNotification(**notification.dict())
    db.add(db_notif)
    db.commit()
    db.refresh(db_notif)
    
    # 2. Push to Supabase for real-time
    # Use user_id from schema if present, otherwise handle appropriately
    # The frontend usually sends customer_id for broadcasts
    notify_target = str(notification.user_id) if notification.user_id else str(notification.customer_id)
    notify_supabase(notify_target, notification.message)
    
    return db_notif

@router.get("/notifications", response_model=PaginatedResponse[schemas.NotificationWithCustomer])
def get_notifications(page: int = 1, size: int = 10, db: Session = Depends(get_db), _=Depends(RoleChecker(ALL_ROLES))):
    query = db.query(schemas.DBNotification, DBCustomer.name).join(DBCustomer)
    
    # We probably want latest notifications first
    query = query.order_by(schemas.DBNotification.sent_at.desc())
    
    total = query.count()
    pages = (total + size - 1) // size if size > 0 else 0
    if size > 0:
        results = query.offset((page - 1) * size).limit(size).all()
    else:
        results = query.all()
    items = []
    for row in results:
        notif, cust_name = row
        items.append(schemas.NotificationWithCustomer(
            **notif.__dict__,
            customer_name=cust_name
        ))
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": pages
    }

@router.post("/notifications/read-all")
def mark_all_as_read(db: Session = Depends(get_db), _=Depends(RoleChecker(ALL_ROLES))):
    db.query(schemas.DBNotification).update({schemas.DBNotification.is_read: True})
    db.commit()
    return {"msg": "All notifications marked as read"}

@router.patch("/notifications/{notif_id}/read")
def mark_as_read(notif_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(RoleChecker(ALL_ROLES))):
    db_notif = db.query(schemas.DBNotification).filter(schemas.DBNotification.id == notif_id).first()
    if not db_notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    db_notif.is_read = True
    db.commit()
    return {"msg": "Notification marked as read"}
