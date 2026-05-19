from api.db_core import engine, Base
# Import all models to ensure they are registered with Base metadata
from api.auth_user.model_users import DBUser, DBRole
from api.customers.model_customers import DBCustomer
from api.billing.model_bills import DBBill
from api.reservations.model_reservations import DBReservation
from api.notifications.model_notifications import DBNotification

def migrate():
    print("Running migrations...")
    try:
        # Laravel's 'php artisan migrate' creates tables if they don't exist
        Base.metadata.create_all(bind=engine)
        print("Migrations completed!")
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
