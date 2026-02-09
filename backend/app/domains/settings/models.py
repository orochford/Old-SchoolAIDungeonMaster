"""Settings model for persistent configuration storage."""

from sqlalchemy import Column, String, Text
from app.core.database import Base
from app.shared.base_model import BaseModel


class AppSetting(Base, BaseModel):
    """Key-value store for application settings that persist across restarts."""

    __tablename__ = "app_settings"

    key = Column(String(255), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
