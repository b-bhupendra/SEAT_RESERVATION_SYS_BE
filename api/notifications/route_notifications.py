from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..db_core import get_db
from . import model_notifications as schemas
from ..customers.model_customers import DBCustomer
from ..auth_user.dependencies import RoleChecker, PermissionChecker
from typing import List
import uuid

router = APIRouter(prefix="/api", tags=["notifications"])

# Permissions
ADMIN_MGR = ["admin", "manager"]
ALL_ROLES = ["admin", "manager", "staff", "customer"]

from ..pagination import PaginatedResponse
from ..supabase_utils import notify_supabase

@router.post("/notifications")
def create_notification(notification: schemas.NotificationBase, db: Session = Depends(get_db), current_user=Depends(PermissionChecker("send_notifications"))):
    user_id = notification.user_id
    customer_id = notification.customer_id
    
    # Resolve customer's user_id from the customers table if not explicitly provided
    if not user_id and customer_id:
        customer = db.query(DBCustomer).filter(DBCustomer.id == customer_id).first()
        if customer:
            user_id = customer.user_id
            
    # 1. Save to SQL DB for history
    db_notif = schemas.DBNotification(
        customer_id=customer_id,
        user_id=user_id,
        message=notification.message,
        is_read=notification.is_read
    )
    db.add(db_notif)
    db.commit()
    db.refresh(db_notif)
    
    # 2. Push to Supabase for real-time (listening key is user_id)
    notify_target = str(user_id) if user_id else str(customer_id)
    notify_supabase(notify_target, notification.message)
    
    return db_notif

@router.get("/notifications", response_model=PaginatedResponse[schemas.NotificationWithCustomer])
def get_notifications(page: int = 1, size: int = 10, db: Session = Depends(get_db), current_user=Depends(RoleChecker(ALL_ROLES))):
    query = db.query(schemas.DBNotification, DBCustomer.name).join(DBCustomer)
    
    # Secure filtering for customers: only show notifications targeted to this specific customer
    if current_user.get("role") == "customer":
        from ..auth_user.model_users import DBUser
        user_record = db.query(DBUser).filter(DBUser.email == current_user.get("sub")).first()
        customer_record = db.query(DBCustomer).filter(DBCustomer.email == current_user.get("sub")).first()
        
        filters = []
        if user_record:
            filters.append(schemas.DBNotification.user_id == user_record.id)
        if customer_record:
            filters.append(schemas.DBNotification.customer_id == customer_record.id)
            
        if filters:
            from sqlalchemy import or_
            query = query.filter(or_(*filters))
        else:
            query = query.filter(schemas.DBNotification.id == None)
            
    # We want latest notifications first
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
def mark_all_as_read(db: Session = Depends(get_db), current_user=Depends(RoleChecker(ALL_ROLES))):
    if current_user.get("role") == "customer":
        from ..auth_user.model_users import DBUser
        user_record = db.query(DBUser).filter(DBUser.email == current_user.get("sub")).first()
        customer_record = db.query(DBCustomer).filter(DBCustomer.email == current_user.get("sub")).first()
        
        filters = []
        if user_record:
            filters.append(schemas.DBNotification.user_id == user_record.id)
        if customer_record:
            filters.append(schemas.DBNotification.customer_id == customer_record.id)
            
        if filters:
            from sqlalchemy import or_
            db.query(schemas.DBNotification).filter(or_(*filters)).update({schemas.DBNotification.is_read: True})
            db.commit()
    else:
        db.query(schemas.DBNotification).update({schemas.DBNotification.is_read: True})
        db.commit()
    return {"msg": "All notifications marked as read"}

@router.patch("/notifications/{notif_id}/read")
def mark_as_read(notif_id: uuid.UUID, db: Session = Depends(get_db), current_user=Depends(RoleChecker(ALL_ROLES))):
    query = db.query(schemas.DBNotification).filter(schemas.DBNotification.id == notif_id)
    
    if current_user.get("role") == "customer":
        from ..auth_user.model_users import DBUser
        user_record = db.query(DBUser).filter(DBUser.email == current_user.get("sub")).first()
        customer_record = db.query(DBCustomer).filter(DBCustomer.email == current_user.get("sub")).first()
        
        filters = []
        if user_record:
            filters.append(schemas.DBNotification.user_id == user_record.id)
        if customer_record:
            filters.append(schemas.DBNotification.customer_id == customer_record.id)
            
        if filters:
            from sqlalchemy import or_
            query = query.filter(or_(*filters))
        else:
            raise HTTPException(status_code=403, detail="Unauthorized")
            
    db_notif = query.first()
    if not db_notif:
        raise HTTPException(status_code=404, detail="Notification not found")
    db_notif.is_read = True
    db.commit()
    return {"msg": "Notification marked as read"}
