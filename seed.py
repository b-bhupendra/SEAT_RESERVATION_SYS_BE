import os
import uuid
from datetime import datetime, timedelta
import bcrypt
from sqlalchemy.orm import Session
from api.db_core import engine, Base, SessionLocal

# Import all models to ensure metadata is registered
from api.auth_user.model_users import DBUser, DBRole
from api.billing.model_plans import DBPlan
from api.customers.model_customers import DBCustomer
from api.reservations.model_reservations import DBReservation
from api.billing.model_bills import DBBill
from api.notifications.model_notifications import DBNotification
from api.settings.model_settings import DBSetting
from api.reservations.model_seats import DBSeat

def seed_db():
    print("Dropping existing tables...")
    Base.metadata.drop_all(bind=engine)
    
    print("Creating tables with new schema...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        print("Seeding System Roles...")
        roles_data = [
            {"name": "admin", "description": "Full System Access", "permissions": "*"},
            {"name": "manager", "description": "Department Manager", "permissions": "view_dashboard,manage_reservations,manage_customers,view_billing,manage_billing,view_notifications,approve_cash_payment,send_notifications"},
            {"name": "staff", "description": "Floor Staff", "permissions": "manage_reservations,manage_customers,view_billing,view_notifications,approve_cash_payment"},
            {"name": "customer", "description": "Seat Occupant", "permissions": "view_portal,view_notifications"}
        ]
        for r_data in roles_data:
            db.add(DBRole(**r_data))
        db.commit()

        print("Seeding Users...")
        # Password hashing utility
        def hash_pass(p):
            return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
            
        admin = DBUser(email="admin@lumina.pro", hashed_password=hash_pass("admin123"), role="admin")
        manager = DBUser(email="manager@lumina.pro", hashed_password=hash_pass("manager123"), role="manager")
        staff = DBUser(email="staff@lumina.pro", hashed_password=hash_pass("staff123"), role="staff")
        db.add_all([admin, manager, staff])
        db.commit()


        print("Seeding Plans...")
        p1 = DBPlan(name="Daily Pass", description="24 hour access", cost=500)
        p2 = DBPlan(name="Monthly Premium", description="24/7 dedicated seat", cost=1500)
        p3 = DBPlan(name="Quarterly Elite", description="Dedicated cabin & 24/7 access", cost=4000)
        db.add_all([p1, p2, p3])
        db.commit()

        print("Seeding Customers...")
        # Active Customer
        c1 = DBCustomer(
            name="John Active", 
            email="john@example.com", 
            phone="1112223333", 
            status="active"
        )
        c_user1 = DBUser(email="john@example.com", hashed_password=hash_pass("customer123"), role="customer")
        db.add(c_user1)
        db.commit()
        c1.user_id = c_user1.id
        
        # Pending Customer
        c2 = DBCustomer(
            name="Alice Pending", 
            email="alice@example.com", 
            phone="4445556666", 
            status="pending"
        )
        c_user2 = DBUser(email="alice@example.com", hashed_password=hash_pass("customer123"), role="customer")
        db.add(c_user2)
        db.commit()
        c2.user_id = c_user2.id
        
        db.add_all([c1, c2])
        db.commit()

        print("Seeding Reservations...")
        # Active Reservation for John
        now = datetime.utcnow()
        r1 = DBReservation(
            customer_id=c1.id,
            seat_number="A-01",
            subsection="Quiet Zone",
            start_date=now - timedelta(days=5),
            end_date=now + timedelta(days=25), # 25 days left
            status="paid"
        )
        
        # Expiring soon reservation for simulated testing
        c3 = DBCustomer(
            name="Bob Expiring", 
            email="bob@example.com", 
            phone="7778889999", 
            status="active"
        )
        c_user3 = DBUser(email="bob@example.com", hashed_password=hash_pass("customer123"), role="customer")
        db.add(c_user3)
        db.commit()
        c3.user_id = c_user3.id
        db.add(c3)
        db.commit()

        r2 = DBReservation(
            customer_id=c3.id,
            seat_number="B-12",
            subsection="Collaborative",
            start_date=now - timedelta(days=28),
            end_date=now + timedelta(days=2), # Only 2 days left - Should trigger Siren
            status="paid"
        )
        db.add_all([r1, r2])
        db.commit()

        print("Seeding Bills...")
        b1 = DBBill(
            customer_id=c1.id,
            amount=1500,
            status="paid",
            pay_via="UPI",
            due_date=now - timedelta(days=5),
            month_ending=now + timedelta(days=25)
        )
        # Unpaid bill
        b2 = DBBill(
            customer_id=c3.id,
            amount=1500,
            status="pending",
            pay_via="Card",
            due_date=now + timedelta(days=2),
            month_ending=now + timedelta(days=32)
        )
        db.add_all([b1, b2])
        db.commit()

        print("Seeding Settings...")
        hold_setting = DBSetting(key="seat_hold_duration_minutes", value="15")
        db.add(hold_setting)
        
        org_config = DBSetting(
            key="organizations_config", 
            value='{"Trisha Library": ["Premium Zone", "General Area", "Reading Room"], "G2 Library": ["Main Hall", "Quiet Zone"]}'
        )
        db.add(org_config)
        
        transfer_fee_setting = DBSetting(key="customer_transfer_fee", value="500")
        db.add(transfer_fee_setting)
        
        db.commit()

        print("Seeding Seats...")
        seats_to_seed = []
        
        # Premium Zone Seats (TL-PM-001 to 010)
        for i in range(1, 11):
            seats_to_seed.append(DBSeat(seat_number=f"TL-PM-{i:03d}", organization="Trisha Library", sub_organization="Premium Zone"))
            
        # General Area Seats (TL-GA-001 to 010)
        for i in range(1, 11):
            seats_to_seed.append(DBSeat(seat_number=f"TL-GA-{i:03d}", organization="Trisha Library", sub_organization="General Area"))
            
        # Reading Room Seats (TL-RR-001 to 010)
        for i in range(1, 11):
            seats_to_seed.append(DBSeat(seat_number=f"TL-RR-{i:03d}", organization="Trisha Library", sub_organization="Reading Room"))
            
        db.add_all(seats_to_seed)
        db.commit()

        print("Database Seeding Completed Successfully!")
    except Exception as e:
        print(f"Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()
