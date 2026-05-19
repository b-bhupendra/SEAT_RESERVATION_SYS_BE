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
        
    # 2. Revenue by Day / Month Aggregation
    is_sqlite = db.bind.dialect.name == "sqlite"
    if is_sqlite:
        # SQLite lacks native string formatting extractions, handle gracefully on worker side
        bills_query = db.query(DBBill.due_date, DBBill.amount)
        if start_date: bills_query = bills_query.filter(DBBill.due_date >= start_date)
        if end_date: bills_query = bills_query.filter(DBBill.due_date <= end_date)
        bills = bills_query.all()
        
        rev_map = {}
        for b_date, b_amt in bills:
            month_str = "Mon"
            if isinstance(b_date, datetime):
                month_str = b_date.strftime("%b")
            elif isinstance(b_date, str) and len(b_date) >= 7:
                try:
                    dt = datetime.fromisoformat(b_date.split('T')[0])
                    month_str = dt.strftime("%b")
                except:
                    month_str = "Mon"
            rev_map[month_str] = rev_map.get(month_str, 0.0) + float(b_amt or 0)
        
        revenue_by_day = [{"name": k, "Revenue": v} for k, v in rev_map.items()]
    else:
        # Pure SQL Engine-side Filtering, Grouping, and Summation for PostgreSQL
        revenue_query = db.query(
            func.trim(func.to_char(DBBill.due_date, "Mon")).label("name"),
            func.sum(DBBill.amount).label("Revenue")
        )
        if start_date: revenue_query = revenue_query.filter(DBBill.due_date >= start_date)
        if end_date: revenue_query = revenue_query.filter(DBBill.due_date <= end_date)
        
        # Grouping natively inside the SQL engine
        revenue_results = revenue_query.group_by(
            func.trim(func.to_char(DBBill.due_date, "Mon")),
            func.extract('month', DBBill.due_date)
        ).order_by(func.extract('month', DBBill.due_date)).all()
        
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

    # 4. Occupancy / Reservations by Zone (Sub-Organization)
    zone_query = db.query(
        DBReservation.sub_organization.label("name"),
        func.count(DBReservation.id).label("value")
    ).filter(DBReservation.status != "cancelled")
    if start_date: zone_query = zone_query.filter(DBReservation.start_date >= start_date)
    if end_date: zone_query = zone_query.filter(DBReservation.start_date <= end_date)
    zone_results = zone_query.group_by(DBReservation.sub_organization).all()
    occupancy_by_zone = [{"name": z.name or "General Area", "value": z.value} for z in zone_results]
    if not occupancy_by_zone:
        occupancy_by_zone = [{"name": "Premium Zone", "value": 0}, {"name": "General Area", "value": 0}, {"name": "Reading Room", "value": 0}]

    # 5. Reservation Status Breakdown
    status_query = db.query(
        DBReservation.status.label("name"),
        func.count(DBReservation.id).label("value")
    )
    if start_date: status_query = status_query.filter(DBReservation.start_date >= start_date)
    if end_date: status_query = status_query.filter(DBReservation.start_date <= end_date)
    status_results = status_query.group_by(DBReservation.status).all()
    reservation_status = [{"name": s.name or "Unknown", "value": s.value} for s in status_results]

    return {
        "total_customers": total_customers,
        "active_reservations": active_reservations,
        "total_revenue": total_revenue,
        "usage_rate": usage_rate,
        "revenue_by_day": revenue_by_day,
        "payments_overview": payments_overview,
        "occupancy_by_zone": occupancy_by_zone,
        "reservation_status": reservation_status
    }

