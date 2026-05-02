from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import sys
import os

# Add the project directory to sys.path
sys.path.append(r'd:\project\SEAT_RESERVATION_SYS_BE')

from api.auth_user.model_users import DBUser, DBRole

engine = create_engine("sqlite:///d:/project/SEAT_RESERVATION_SYS_BE/sql_app.db")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

print("--- Roles ---")
roles = db.query(DBRole).all()
for r in roles:
    print(f"Name: {r.name}, Permissions: {r.permissions}")

print("\n--- Users ---")
users = db.query(DBUser).all()
for u in users:
    print(f"Email: {u.email}, Role: {u.role}")

db.close()
