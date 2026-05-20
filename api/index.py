import os # Server heartbeat: PhonePe simulation mode enabled
import sys
import uuid
from fastapi import FastAPI, HTTPException, status, Depends
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session

# Ensure parent directory is in sys.path so 'app' module can be imported on Vercel
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

load_dotenv()
from .auth_user.route_users import router as user_router
from .customers.route_customers import router as customer_router
from .billing.route_bills import router as billing_router
from .billing.route_plans import router as plans_router
from .reservations.route_reservations import router as reservation_router
from .notifications.route_notifications import router as notification_router
from .dashboard.route_dashboard import router as dashboard_router
from app.routers.billing import router as payment_router
from .settings.route_settings import router as settings_router
from .reservations.route_seats import router as seats_router

from .db_core import engine, Base, get_db
# Import models here to ensure they are registered with Base metadata for table creation
from .customers.model_customers import DBCustomer
from .reservations.model_reservations import DBReservation
from .billing.model_bills import DBBill, DBTransaction
from .billing.model_plans import DBPlan
from .notifications.model_notifications import DBNotification
from .settings.model_settings import DBSetting
from .reservations.model_seats import DBSeat

from .supabase_utils import supabase_client

class NotificationNotify(BaseModel):
    user_id: uuid.UUID
    message: str

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Warning: Database tables could not be created automatically: {e}")
    yield

app = FastAPI(title="Lumina Pro API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router)
app.include_router(customer_router)
app.include_router(billing_router)
app.include_router(plans_router)
app.include_router(reservation_router)
app.include_router(notification_router)
app.include_router(dashboard_router)
app.include_router(payment_router)
app.include_router(settings_router)
app.include_router(seats_router)

from sqlalchemy import text

@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    return {"status": "ok", "db": db_status, "supabase": "ready" if supabase_client else "not configured"}

@app.post("/api/notify", status_code=status.HTTP_201_CREATED, tags=["notifications"])
async def notify_realtime(notification: NotificationNotify):
    """
    Securely inserts a notification into Supabase for real-time broadcasting.
    Requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables.
    """
    if not supabase_client:
        raise HTTPException(status_code=503, detail="Supabase real-time service not configured")
    
    try:
        response = supabase_client.table("notifications").insert({
            "user_id": notification.user_id, # Supabase handles UUID strings
            "message": notification.message,
            "is_read": False
        }).execute()
        return {"status": "success", "data": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
