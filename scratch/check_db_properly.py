import os
import sys
# Add backend to path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(backend_path)

from api.db_core import SessionLocal
from api.auth_user.model_users import DBUser
from api.customers.model_customers import DBCustomer
from api.reservations.model_reservations import DBReservation

db = SessionLocal()
try:
    print("--- Users ---")
    users = db.query(DBUser).all()
    for u in users:
        print(f"ID: {u.id}, Email: {u.email}, Role: {u.role}")

    print("\n--- Customers ---")
    customers = db.query(DBCustomer).all()
    for c in customers:
        print(f"ID: {c.id}, Name: {c.name}, Email: {c.email}, Status: {c.status}")

    print("\n--- Reservations ---")
    res = db.query(DBReservation).all()
    for r in res:
        print(f"ID: {r.id}, CustomerID: {r.customer_id}, Seat: {r.seat_number}, Status: {r.status}, End: {r.end_date}")
finally:
    db.close()
