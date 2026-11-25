from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from backend.app.core.database import Base


class AdminUser(Base):
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(64), unique=True, index=True, nullable=False, comment="管理员登录用户名")
    password_hash = Column(String(256), nullable=False, comment="bcrypt 密码哈希")
    role = Column(String(32), default="admin", nullable=False, comment="角色")
    is_active = Column(Boolean, default=True, nullable=False, comment="账号是否启用")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
