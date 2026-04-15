from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..db_core import Base
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# SQLAlchemy Models
class DBBill(Base):
    __tablename__ = "bills"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    amount = Column(Float)
    month_ending = Column(DateTime)
    due_date = Column(DateTime)
    pay_via = Column(String, nullable=True)
    pay_date = Column(DateTime, nullable=True)
    status = Column(String, default="pending")

# Pydantic Models
class BillBase(BaseModel):
    customer_id: uuid.UUID
    amount: float
    month_ending: datetime
    due_date: datetime
    pay_via: Optional[str] = None
    status: str = "pending"

class Bill(BillBase):
    id: uuid.UUID
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    pay_date: Optional[datetime] = None
    class Config:
        from_attributes = True

class BillCreate(BaseModel):
    customer_id: uuid.UUID
    amount: float
    month_ending: datetime
    due_date: datetime
    pay_via: str

class BillStatusUpdate(BaseModel):
    status: str
