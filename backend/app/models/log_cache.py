from __future__ import annotations
from sqlalchemy import Column, Integer, BigInteger, String, Boolean, Index
from backend.app.core.database import Base


class UsageLogCache(Base):
    __tablename__ = "usage_logs_cache"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    new_api_log_id = Column(Integer, unique=True, index=True, nullable=False, comment="new-api 原始日志 ID，用于幂等去重")
    token_name = Column(String(128), index=True, nullable=False, comment="Token 名称")
    emp_no = Column(String(64), index=True, nullable=False, comment="对应工号")
    model_name = Column(String(128), index=True, nullable=False, comment="模型标识")
    prompt_tokens = Column(Integer, default=0, nullable=False, comment="输入 Token 数")
    completion_tokens = Column(Integer, default=0, nullable=False, comment="输出 Token 数")
    quota = Column(BigInteger, default=0, nullable=False, comment="消耗额度/点数")
    use_time = Column(Integer, default=0, nullable=False, comment="请求耗时(ms)")
    is_stream = Column(Boolean, default=False, nullable=False, comment="是否流式请求")
    created_at = Column(BigInteger, index=True, nullable=False, comment="Unix 时间戳(秒)")

    __table_args__ = (
        Index("ix_usage_emp_time", "emp_no", "created_at"),
        Index("ix_usage_model_time", "model_name", "created_at"),
    )
