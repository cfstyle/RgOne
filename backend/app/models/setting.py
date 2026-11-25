from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime
from backend.app.core.database import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True, index=True, comment="配置键名")
    value = Column(Text, nullable=True, comment="配置值(JSON/纯文本)")
    description = Column(String(256), nullable=True, comment="配置描述说明")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
