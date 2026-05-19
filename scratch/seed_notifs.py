import sys
import os
import random
import uuid

# Add current directory to path
sys.path.append(os.getcwd())

from api.db_core import SessionLocal
from api.customers.model_customers import DBCustomer
from api.notifications.model_notifications import DBNotification
from api.auth_user.model_users import DBUser, DBRole
from database.factories.notification_factory import NotificationFactory

def seed_notifications():
    db = SessionLocal()
    try:
        # Check for customers
        customer_ids = [c.id for c in db.query(DBCustomer.id).limit(20).all()]
        if not customer_ids:
            print("ERROR: No customers found in database. Please seed customers first.")
            return

        print(f"Found {len(customer_ids)} customers. Seeding 50 notifications...")
        
        factory = NotificationFactory(db)
        for i in range(50):
            data = factory.definition()
            data["customer_id"] = random.choice(customer_ids)
            # Ensure ID is unique and valid UUID
            data["id"] = uuid.uuid4()
            
            db_notif = DBNotification(**data)
            db.add(db_notif)
            
            if (i + 1) % 10 == 0:
                print(f"Added {i+1} notifications...")
        
        db.commit()
        print("Successfully seeded 50 notifications!")
    except Exception as e:
        print(f"Seeding failed: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_notifications()
