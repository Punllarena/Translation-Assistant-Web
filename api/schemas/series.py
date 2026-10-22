from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from api.core.volume_names import validate_template
from api.schemas.common import Credit, Patch, Title


class SeriesCreate(BaseModel):
    title: Title
    syosetu_url: str = ""
    original_title: Credit = ""
    original_author: Credit = ""
    author_romaji: Credit = ""


class SeriesUpdate(Patch):
    NULLABLE: ClassVar[frozenset[str]] = frozenset({"wp_password_enabled", "wp_unlock_after"})

    title: Title | None = None
    syosetu_url: str | None = None
    original_title: Credit | None = None
    original_author: Credit | None = None
    author_romaji: Credit | None = None
    wp_series_slug: str | None = None
    wp_series_title_short: str | None = None
    wp_password_enabled: bool | None = None
    wp_unlock_after: int | None = Field(default=None, ge=0, le=2**31 - 1)
    volume_title_template: str | None = Field(default=None, max_length=300)  # "" resets

    @field_validator("volume_title_template")
    @classmethod
    def _template_is_valid(cls, v: str | None) -> str | None:
        if v:
            validate_template(v)
        return v


class SeriesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    syosetu_url: str
    original_title: str
    original_author: str
    author_romaji: str
    wp_series_slug: str
    wp_series_title_short: str
    wp_password_enabled: bool | None
    wp_unlock_after: int | None
    syosetu_volume_mode: str
    syosetu_volume_marker: str
    volume_title_template: str
    volume_title_template_effective: str
    created_at: datetime
