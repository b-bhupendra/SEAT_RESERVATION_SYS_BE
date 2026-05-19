from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..db_core import Base
from pydantic import BaseModel
from typing import Optional

class DBSeat(Base):
    __tablename__ = "seats"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seat_number = Column(String, nullable=False)
    organization = Column(String, nullable=False)
    sub_organization = Column(String, nullable=False)

class SeatBase(BaseModel):
    seat_number: str
    organization: str
    sub_organization: str

class Seat(SeatBase):
    id: uuid.UUID
    status: Optional[str] = "available" # Dynamically calculated: available, held, paid
    held_by_customer_id: Optional[uuid.UUID] = None # Dynamically calculated
    held_by_customer_name: Optional[str] = None # Dynamically calculated
    expires_at: Optional[str] = None # Dynamically calculated

    class Config:
        from_attributes = True

class SeatGenerateRequest(BaseModel):
    organization: str
    sub_organization: str
    prefix: str
    count: int
