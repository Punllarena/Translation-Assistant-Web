from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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


class SuggestionOut(BaseModel):
    """A line's held suggestion; `stale` when the line's source changed since it was sent."""

    line_number: int
    text: str
    stale: bool
    chunk_id: int
    first_line: int
    last_line: int
    model: str
    created_at: datetime


class ChunkOut(BaseModel):
    """One Ollama request: its settings, timings, outcome counters, reasoning and prompt."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    series_id: int | None
    document_id: int | None
    job_id: int | None
    source: str
    ok: bool
    clamped: bool
    depth: int
    model: str
    preset: str
    chunk_lines: int
    context_lines: int
    first_line: int
    last_line: int
    asked: int
    prompt_tokens: int
    output_tokens: int
    prompt_ms: int | None
    eval_ms: int | None
    load_ms: int | None
    total_ms: int | None
    first_token_ms: int | None
    used_count: int
    edited_count: int
    ignored_count: int
    reasoning: str | None
    prompt: str | None
    created_at: datetime
