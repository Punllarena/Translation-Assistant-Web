from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Patch, Title


class SeriesCreate(BaseModel):
    title: Title
    profile_id: int | None = None
    syosetu_url: str = ""


class SeriesUpdate(Patch):
    NULLABLE: ClassVar[frozenset[str]] = frozenset(
        {"profile_id", "wp_password_enabled", "wp_unlock_after"}
    )

    title: Title | None = None
    profile_id: int | None = None
    syosetu_url: str | None = None
    wp_series_slug: str | None = None
    wp_series_title_short: str | None = None
    wp_password_enabled: bool | None = None
    wp_unlock_after: int | None = Field(default=None, ge=0, le=2**31 - 1)


class SeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    profile_id: int | None
    syosetu_url: str
    wp_series_slug: str
    wp_series_title_short: str
    wp_password_enabled: bool | None
    wp_unlock_after: int | None
    created_at: datetime
