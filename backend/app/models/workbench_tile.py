from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint

from backend.app.core.database import Base


class WorkbenchTile(Base):
    __tablename__ = "workbench_tiles"
    __table_args__ = {"sqlite_autoincrement": True}

    id = Column(Integer, primary_key=True)
    owner_emp_no = Column(String(64), index=True, nullable=True)
    title = Column(String(100), nullable=False)
    subtitle = Column(String(240), nullable=False, default="")
    tile_type = Column(String(16), nullable=False)
    icon = Column(String(32), nullable=False)
    payload = Column(Text, nullable=False)
    category = Column(String(64), nullable=True)
    sort_order = Column(Integer, default=0, nullable=False)
    is_enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class UserHiddenPresetTile(Base):
    __tablename__ = "user_hidden_preset_tiles"
    __table_args__ = (UniqueConstraint("emp_no", "tile_id"),)

    id = Column(Integer, primary_key=True)
    emp_no = Column(String(64), nullable=False)
    tile_id = Column(ForeignKey("workbench_tiles.id", ondelete="CASCADE"), index=True, nullable=False)
