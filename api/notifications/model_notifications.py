from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..db_core import Base
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# SQLAlchemy Models
class DBNotification(Base):
    __tablename__ = "notifications"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id = Column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    message = Column(String)
    is_read = Column(Boolean, default=False)
    sent_at = Column(DateTime, default=datetime.utcnow)

# Pydantic Models
class NotificationBase(BaseModel):
    customer_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    message: str
    is_read: bool = False

class Notification(NotificationBase):
    id: uuid.UUID
    sent_at: datetime
    class Config:
        from_attributes = True

class NotificationWithCustomer(Notification):
    customer_name: Optional[str] = None
