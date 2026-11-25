from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from backend.app.core.database import Base


class AuthLockout(Base):
    __tablename__ = "auth_lockouts"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    target_type = Column(String(16), nullable=False, comment="emp_no 或 ip")
    target_val = Column(String(128), index=True, nullable=False, comment="工号或客户端 IP")
    fail_count = Column(Integer, default=1, nullable=False, comment="连续输错次数")
    locked_until = Column(DateTime, nullable=True, comment="锁定截止时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
