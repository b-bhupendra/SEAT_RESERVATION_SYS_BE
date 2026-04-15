import os
from sqlalchemy import create_engine
from api.db_core import engine, Base
# Import all models to ensure they are registered
from api.auth_user.model_users import DBUser, DBRole
from api.customers.model_customers import DBCustomer
from api.reservations.model_reservations import DBReservation
from api.billing.model_bills import DBBill
from api.notifications.model_notifications import DBNotification

def drop_all():
    print("Dropping all tables for fresh UUID migration...")
    Base.metadata.drop_all(bind=engine)
    print("Re-creating tables with UUID schema...")
    Base.metadata.create_all(bind=engine)
    print("Sync complete.")

if __name__ == "__main__":
    drop_all()
