from sqlalchemy import Column, String
from sqlalchemy.dialects.postgresql import UUID
import uuid
from ..db_core import Base
from pydantic import BaseModel
from typing import Optional

# SQLAlchemy Models
class DBUser(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String)  # admin, manager, staff
    full_name = Column(String)

class DBRole(Base):
    __tablename__ = "roles"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True)
    description = Column(String)
    permissions = Column(String) # Comma separated list of permissions

# Pydantic Models
class UserBase(BaseModel):
    email: str
    role: str
    full_name: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class User(UserBase):
    id: uuid.UUID
    class Config:
        from_attributes = True

class RoleBase(BaseModel):
    name: str
    description: str
    permissions: str

class Role(RoleBase):
    id: uuid.UUID
    class Config:
        from_attributes = True
