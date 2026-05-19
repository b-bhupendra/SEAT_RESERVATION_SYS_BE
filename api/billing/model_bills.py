from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean
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
    # Cash payment fields
    cash_due_date = Column(DateTime, nullable=True)   # deadline admin sets for cash delivery
    notes = Column(String, nullable=True)              # admin notes / instructions

class DBTransaction(Base):
    __tablename__ = "payment_transactions"
    transaction_id = Column(String, primary_key=True)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"))
    amount = Column(Float)
    status = Column(String, default="PENDING")
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Pydantic Models
class BillBase(BaseModel):
    customer_id: uuid.UUID
    amount: float
    month_ending: datetime
    due_date: datetime
    pay_via: Optional[str] = None
    status: str = "pending"
    cash_due_date: Optional[datetime] = None
    notes: Optional[str] = None

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

# ── Cash Payment Pydantic Models ─────────────────────────────────────────────
class CashPaymentRequest(BaseModel):
    customer_id: uuid.UUID
    amount: float
    seat_number: str
    organization: str
    sub_organization: str
    notes: Optional[str] = None   # customer notes / instructions for admin

class CashApproveRequest(BaseModel):
    cash_due_hours: int           # how many hours customer has to deliver cash
    notes: Optional[str] = None   # admin note to customer (e.g. "Bring to front desk")

class CashConfirmRequest(BaseModel):
    notes: Optional[str] = None   # confirmation note
