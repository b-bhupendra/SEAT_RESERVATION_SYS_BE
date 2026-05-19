from sqlalchemy import Column, String
from ..db_core import Base
from pydantic import BaseModel

class DBSetting(Base):
    __tablename__ = "settings"
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)

class SettingBase(BaseModel):
    key: str
    value: str

class SettingUpdate(BaseModel):
    value: str

class Setting(SettingBase):
    class Config:
        from_attributes = True
