from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..db_core import Base
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# SQLAlchemy Models
class DBReservation(Base):
    __tablename__ = "reservations"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    subsection = Column(String)
    seat_number = Column(String)
    start_date = Column(DateTime)
    end_date = Column(DateTime, nullable=True)
    duration_months = Column(Integer, default=1)
    amount = Column(Float)
    pay_via = Column(String, default="Cash")
    status = Column(String, default="paid")
    organization = Column(String, nullable=True)
    sub_organization = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic Models
class ReservationBase(BaseModel):
    customer_id: uuid.UUID
    subsection: str
    seat_number: str
    start_date: datetime
    end_date: Optional[datetime] = None
    duration_months: int = 1
    amount: Optional[float] = 0.0
    pay_via: str = "Cash"
    status: str = "paid"
    organization: Optional[str] = None
    sub_organization: Optional[str] = None
    created_at: Optional[datetime] = None

class Reservation(ReservationBase):
    id: uuid.UUID
    class Config:
        from_attributes = True

class ReservationWithCustomer(Reservation):
    customer_name: Optional[str] = None

class ReservationStatusUpdate(BaseModel):
    status: str
