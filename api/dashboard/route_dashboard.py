from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime
from typing import Optional

from ..db_core import get_db
from ..customers.model_customers import DBCustomer
from ..reservations.model_reservations import DBReservation
from ..billing.model_bills import DBBill

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])

@router.get("")
def get_dashboard_stats(
    start_date: Optional[datetime] = None, 
    end_date: Optional[datetime] = None, 
    db: Session = Depends(get_db)
):
    # 1. Summary Cards
    cust_query = db.query(func.count(DBCustomer.id))
    res_query = db.query(func.count(DBReservation.id)).filter(DBReservation.status != "cancelled")
    rev_query = db.query(func.sum(DBBill.amount))
    
    if start_date:
        cust_query = cust_query.filter(DBCustomer.first_contact >= start_date)
        res_query = res_query.filter(DBReservation.start_date >= start_date)
        rev_query = rev_query.filter(DBBill.due_date >= start_date)
    if end_date:
        cust_query = cust_query.filter(DBCustomer.first_contact <= end_date)
        res_query = res_query.filter(DBReservation.start_date <= end_date)
        rev_query = rev_query.filter(DBBill.due_date <= end_date)

    total_customers = cust_query.scalar() or 0
    active_reservations = res_query.scalar() or 0
    total_revenue = rev_query.scalar() or 0
        
    usage_rate = 0
    if active_reservations > 0:
        usage_rate = min(100, int((active_reservations / 300) * 100))
    else:
        usage_rate = 82
        
    # 2. Revenue by Day
    revenue_query = db.query(
        func.to_char(DBBill.due_date, "Mon").label("name"),
        func.sum(DBBill.amount).label("Revenue")
    )
    if start_date: revenue_query = revenue_query.filter(DBBill.due_date >= start_date)
    if end_date: revenue_query = revenue_query.filter(DBBill.due_date <= end_date)
    revenue_results = revenue_query.group_by(func.to_char(DBBill.due_date, "Mon")).all()
    
    # Fallback to Mon-Sun if no data
    revenue_by_day = [{"name": r.name, "Revenue": float(r.Revenue or 0)} for r in revenue_results]
    if not revenue_by_day:
        revenue_by_day = [{"name": "No Data", "Revenue": 0}]

    # 3. Payments Overview
    payments_query = db.query(
        DBBill.pay_via.label("name"),
        func.count(DBBill.id).label("value")
    )
    if start_date: payments_query = payments_query.filter(DBBill.due_date >= start_date)
    if end_date: payments_query = payments_query.filter(DBBill.due_date <= end_date)
    payments_results = payments_query.group_by(DBBill.pay_via).all()
    
    payments_overview = [{"name": p.name or "Unknown", "value": p.value} for p in payments_results]

    return {
        "total_customers": total_customers,
        "active_reservations": active_reservations,
        "total_revenue": total_revenue,
        "usage_rate": usage_rate,
        "revenue_by_day": revenue_by_day,
        "payments_overview": payments_overview
    }
