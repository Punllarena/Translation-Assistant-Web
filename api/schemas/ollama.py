from typing import Literal

from pydantic import BaseModel, Field


class QueueItemIn(BaseModel):
    kind: Literal["series", "volume", "documents"]
    series_id: int
    volume_id: int | None = None
    document_ids: list[int] = Field(default_factory=list, max_length=1000)


class QueueItemOut(BaseModel):
    id: int
    kind: str
    series_id: int
    series_title: str
    volume_id: int | None
    volume_label: str | None
    document_ids: list[int]
    label: str
    lines_left: int
    estimate_seconds: int | None


class QueueOrder(BaseModel):
    ids: list[int]


class FlushIn(BaseModel):
    document_ids: list[int] | None = None
    volume_id: int | None = None
    series_id: int | None = None


class FlushOut(BaseModel):
    cleared: int
