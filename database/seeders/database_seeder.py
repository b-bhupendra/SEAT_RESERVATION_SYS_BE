import sys
import os
from sqlalchemy.orm import Session
from api.db_core import SessionLocal, engine, Base
from database.factories.user_factory import UserFactory
from database.factories.customer_factory import CustomerFactory
from database.factories.bill_factory import BillFactory
from database.factories.reservation_factory import ReservationFactory
from database.factories.notification_factory import NotificationFactory
from api.customers.model_customers import DBCustomer
import random

class DatabaseSeeder:
    def __init__(self):
        self.db: Session = SessionLocal()

    def run(self):
        print("Starting database seeding...")
        
        # 0. Clear existing data to ensure exact 5000 records
        print("Clearing existing data...")
        from api.auth_user.model_users import DBUser, DBRole
        from api.customers.model_customers import DBCustomer
        from api.billing.model_bills import DBBill
        from api.reservations.model_reservations import DBReservation
        from api.notifications.model_notifications import DBNotification

        # Truncate tables for a clean slate
        # Note: Delete order matters for foreign keys
        self.db.query(DBNotification).delete()
        self.db.query(DBBill).delete()
        self.db.query(DBReservation).delete()
        self.db.query(DBCustomer).delete()
        self.db.query(DBUser).delete()
        self.db.query(DBRole).delete()
        self.db.commit()

        # 1. Seed Roles and Admin User
        print("Seeding Admin User...")
        user_factory = UserFactory(self.db)
        user_factory.create_admin(email="admin@admin.com", password="admin")
        
        # 2. Seed Customers (100)
        print("Seeding 100 Customers...")
        customer_factory = CustomerFactory(self.db)
        customer_factory.create_many(100)
        
        # Fetch all customer IDs for linking
        customer_ids = [c.id for c in self.db.query(DBCustomer.id).all()]
        
        # 3. Seed Bills (100)
        print("Seeding 100 Bills...")
        bill_factory = BillFactory(self.db)
        bills = []
        for _ in range(100):
            bill_data = bill_factory.definition()
            bill_data["customer_id"] = random.choice(customer_ids)
            bills.append(bill_data)
        
        # Batch insert bills
        batch_size = 500
        for i in range(0, len(bills), batch_size):
             self.db.bulk_insert_mappings(bill_factory.model, bills[i:i+batch_size])
             self.db.commit()
 
        # 4. Seed Reservations (100)
        print("Seeding 100 Reservations...")
        res_factory = ReservationFactory(self.db)
        reservations = []
        for _ in range(100):
            res_data = res_factory.definition()
            res_data["customer_id"] = random.choice(customer_ids)
            reservations.append(res_data)
        
        for i in range(0, len(reservations), batch_size):
            self.db.bulk_insert_mappings(res_factory.model, reservations[i:i+batch_size])
            self.db.commit()
 
        # 5. Seed Notifications (100)
        print("Seeding 100 Notifications...")
        notif_factory = NotificationFactory(self.db)
        notifications = []
        for _ in range(100):
            notif_data = notif_factory.definition()
            notif_data["customer_id"] = random.choice(customer_ids)
            notifications.append(notif_data)
            
        for i in range(0, len(notifications), batch_size):
            self.db.bulk_insert_mappings(notif_factory.model, notifications[i:i+batch_size])
            self.db.commit()

        print("Seeding completed successfully!")
        self.db.close()

if __name__ == "__main__":
    seeder = DatabaseSeeder()
    seeder.run()
