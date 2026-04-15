from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..db_core import Base
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# SQLAlchemy Models
class DBCustomer(Base):
    __tablename__ = "customers"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    status = Column(String, default="active")
    avatar = Column(String, nullable=True)
    first_contact = Column(DateTime, default=datetime.utcnow)

# Pydantic Models
class CustomerBase(BaseModel):
    name: str
    email: str
    phone: str
    status: str = "active"
    avatar: Optional[str] = None

class Customer(CustomerBase):
    id: uuid.UUID
    first_contact: datetime
    class Config:
        from_attributes = True
