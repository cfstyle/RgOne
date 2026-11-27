from __future__ import annotations
from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from backend.app.core.database import Base


class Plugin(Base):
    """企业 DSH 插件市场插件主记录"""

    __tablename__ = "plugins"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, index=True, nullable=False)
    display_name = Column(String(128), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    category = Column(String(64), nullable=False, default="效率工具", index=True)
    tags_json = Column(Text, nullable=False, default="[]")
    icon = Column(String(64), nullable=False, default="Puzzle")
    author_emp_no = Column(String(64), nullable=False, index=True)
    author_name = Column(String(64), nullable=False, default="")
    repo_url = Column(String(512), nullable=False, default="")
    status = Column(String(32), nullable=False, default="pending", index=True)
    latest_version = Column(String(64), nullable=False, default="")
    downloads = Column(Integer, nullable=False, default=0)
    sort_weight = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PluginVersion(Base):
    """企业 DSH 插件版本与安全审核记录"""

    __tablename__ = "plugin_versions"

    id = Column(Integer, primary_key=True, index=True)
    plugin_id = Column(Integer, ForeignKey("plugins.id"), nullable=False, index=True)
    version = Column(String(64), nullable=False)
    tarball_path = Column(String(512), nullable=False, default="")
    tarball_sha256 = Column(String(64), nullable=False, default="")
    package_json_snapshot = Column(Text, nullable=False, default="{}")
    changelog = Column(Text, nullable=False, default="")
    submit_source = Column(String(32), nullable=False, default="tgz")
    review_status = Column(String(32), nullable=False, default="pending", index=True)
    has_lifecycle_scripts = Column(Boolean, nullable=False, default=False)
    reviewed_by = Column(String(64), nullable=False, default="")
    review_comment = Column(Text, nullable=False, default="")
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
