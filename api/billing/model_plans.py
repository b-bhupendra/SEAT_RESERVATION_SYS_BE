from sqlalchemy import Column, String, Integer
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..db_core import Base
from pydantic import BaseModel
from typing import Optional

# SQLAlchemy Models
class DBPlan(Base):
    __tablename__ = "plans"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, index=True)
    description = Column(String, nullable=True)
    cost = Column(Integer) # Cost in lowest denomination or standard integer

# Pydantic Models
class PlanBase(BaseModel):
    name: str
    description: Optional[str] = None
    cost: int

class Plan(PlanBase):
    id: uuid.UUID
    class Config:
        from_attributes = True
