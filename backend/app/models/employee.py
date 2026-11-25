from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import relationship
from backend.app.core.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    emp_no = Column(String(64), unique=True, index=True, nullable=False, comment="员工工号")
    name = Column(String(64), nullable=False, comment="真实完整姓名")
    department = Column(String(128), nullable=False, default="科技部", comment="所属部门")
    phone_last4 = Column(String(4), nullable=True, comment="手机号后4位（可选辅助）")
    is_active = Column(Boolean, default=True, nullable=False, comment="是否有效白名单")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # 关联 Token
    token = relationship("UserToken", back_populates="employee", uselist=False, cascade="all, delete-orphan")
