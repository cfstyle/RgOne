from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text
from backend.app.core.database import Base


class Article(Base):
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String(256), nullable=False, comment="文章标题")
    summary = Column(String(512), nullable=True, comment="文章摘要")
    category = Column(String(64), default="入门指南", nullable=False, comment="分类（如 入门指南/提效秘籍/代码实践）")
    tags = Column(String(256), default="[]", nullable=False, comment="标签 JSON 数组字符串")
    content_md = Column(Text, nullable=False, comment="Markdown 正文")
    author_name = Column(String(64), default="AI 赋能工作组", nullable=False, comment="作者")
    view_count = Column(Integer, default=0, nullable=False, comment="浏览次数")
    is_pinned = Column(Boolean, default=False, nullable=False, comment="是否置顶推荐")
    is_published = Column(Boolean, default=True, nullable=False, comment="是否正式发布")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
