import re
from datetime import datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Subtitle = Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)]
Category = Annotated[str, StringConstraints(strip_whitespace=True, max_length=64)]
Payload = Annotated[str, StringConstraints(min_length=1, max_length=10000)]
TileType = Literal["prompt", "link"]
TileIcon = Literal["Sparkles", "Code", "FileText", "Globe", "Database", "Shield", "Briefcase", "Zap"]
SortOrder = Annotated[int, Field(ge=-2147483648, le=2147483647)]


class TileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title
    subtitle: Subtitle = ""
    tile_type: TileType
    icon: TileIcon = "Sparkles"
    payload: Payload
    category: Category | None = None
    sort_order: SortOrder = 0
    is_enabled: bool = True

    @model_validator(mode="after")
    def validate_payload(self):
        if not self.payload.strip():
            raise ValueError("请填写磁贴内容")
        if self.tile_type == "link":
            url = self.payload.strip()
            if re.search(r"[\s\x00-\x1f\x7f\\]", url):
                raise ValueError("链接包含无效字符")
            if url.startswith("/") and not url.startswith("//"):
                self.payload = url
                return self
            try:
                parts = urlsplit(url)
                valid = (
                    url.lower().startswith(("http://", "https://"))
                    and bool(parts.hostname)
                    and parts.username is None
                    and parts.port != 0
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("链接必须是 HTTP(S) 地址或以 / 开头的站内路径")
            self.payload = url
        return self


class TileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Title | None = None
    subtitle: Subtitle | None = None
    tile_type: TileType | None = None
    icon: TileIcon | None = None
    payload: Payload | None = None
    category: Category | None = None
    sort_order: SortOrder | None = None
    is_enabled: bool | None = None


class TileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_emp_no: str | None
    title: str
    subtitle: str
    tile_type: TileType
    icon: TileIcon
    payload: str
    category: str | None
    sort_order: int
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class TileList(BaseModel):
    tiles: list[TileRead]
    hidden_presets: list[TileRead]


class TileOrder(BaseModel):
    id: Annotated[int, Field(gt=0)]
    sort_order: SortOrder


class TileReorder(BaseModel):
    items: Annotated[list[TileOrder], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_ids(self):
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("排序请求中包含重复磁贴")
        return self
