from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, BigInteger, Boolean, DateTime, Text
from backend.app.core.database import Base


class SharedFile(Base):
    __tablename__ = "shared_files"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    category = Column(String(32), default="installer", nullable=False, comment="installer/manual/plugin/other")
    title = Column(String(128), nullable=False, comment="资料展示标题")
    version = Column(String(64), nullable=True, comment="版本号，如 v1.2.0")
    description = Column(Text, nullable=True, comment="更新说明或简介")
    original_filename = Column(String(256), nullable=False, comment="原始文件名")
    stored_filename = Column(String(256), nullable=False, unique=True, comment="存储安全文件名")
    file_size = Column(BigInteger, default=0, nullable=False, comment="文件字节数")
    sha256 = Column(String(64), nullable=True, comment="文件 SHA256 校验值")
    download_count = Column(Integer, default=0, nullable=False, comment="累计下载次数")
    is_recommended = Column(Boolean, default=False, nullable=False, comment="是否设为首页主推客户端安装包")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
