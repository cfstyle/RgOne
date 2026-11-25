from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class UserToken(Base):
    __tablename__ = "user_tokens"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    emp_no = Column(String(64), ForeignKey("employees.emp_no", ondelete="CASCADE"), unique=True, index=True, nullable=False)
    new_api_token_id = Column(Integer, nullable=True, comment="new-api 对应的 Token ID")
    token_name = Column(String(128), nullable=False, index=True, comment="Token 名称，如 EMP_001024_张三")
    api_key_encrypted = Column(String(512), nullable=False, comment="加密存储的 API Key")
    status = Column(String(32), default="active", nullable=False, comment="active 或 disabled")
    reset_count = Column(Integer, default=0, nullable=False, comment="重置密钥次数")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    employee = relationship("Employee", back_populates="token")
