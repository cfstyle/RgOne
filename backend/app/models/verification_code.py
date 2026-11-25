from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from backend.app.core.database import Base


class VerificationCode(Base):
    __tablename__ = "verification_codes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    emp_no = Column(String(64), index=True, nullable=False, comment="关联员工工号")
    code_hash = Column(String(128), nullable=False, comment="验证码哈希 (SHA-256)")
    expire_at = Column(DateTime, nullable=False, index=True, comment="过期时间戳")
    sent_at = Column(DateTime, nullable=False, comment="发送时间戳，用于冷却计算")
    is_used = Column(Boolean, default=False, nullable=False, index=True, comment="是否已被原子消费")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
