from datetime import datetime
from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.common import Patch, Title

# A long web-novel chapter is ~30k characters; this bounds a pasted body well above that.
MAX_RAW_CHARS = 1_000_000


class DocumentCreate(BaseModel):
    title: Title
    chapter_title: str = ""
    series_id: int | None = None
    volume_id: int | None = None
    source_url: str = ""
    source_language: str = Field(default="ja", min_length=2, max_length=16)
    raw_text: str = Field(default="", max_length=MAX_RAW_CHARS)


class DocumentUpdate(Patch):
    NULLABLE: ClassVar[frozenset[str]] = frozenset({"series_id", "volume_id"})

    title: Title | None = None
    chapter_title: str | None = None
    series_id: int | None = None
    volume_id: int | None = None
    source_url: str | None = None
    source_language: str | None = Field(default=None, min_length=2, max_length=16)
    last_position: int | None = Field(default=None, ge=0)


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    chapter_title: str
    series_id: int | None
    volume_id: int | None
    series_order: int
    source_language: str
    source_url: str
    last_position: int
    wp_status: str
    wp_post_url: str
    created_at: datetime
    updated_at: datetime


class DocumentListItem(DocumentOut):
    """A picker row: the document plus what the picker shows about its progress."""

    line_count: int
    translated_count: int
    image_count: int
    has_cover: bool
    progress: int


class DocumentIds(BaseModel):
    document_ids: list[int] = Field(min_length=1)


class MergeRequest(BaseModel):
    document_ids: list[int] = Field(min_length=2)
    title: Title


class SplitCut(BaseModel):
    start: int
    title: str = ""


class SplitRequest(BaseModel):
    cuts: list[SplitCut] = Field(min_length=1)
