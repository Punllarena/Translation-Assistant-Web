from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


class OllamaChunk(Base):
    """One Ollama request over a chunk of lines: its settings, timings and how it was used."""

    __tablename__ = "ollama_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    series_id: Mapped[int | None] = mapped_column(ForeignKey("series.id", ondelete="SET NULL"))
    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[int | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(8), nullable=False)  # run / manual / reroll
    ok: Mapped[bool] = mapped_column(Boolean, nullable=False)
    clamped: Mapped[bool] = mapped_column(Boolean, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    preset: Mapped[str] = mapped_column(String(16), nullable=False)
    chunk_lines: Mapped[int] = mapped_column(Integer, nullable=False)
    context_lines: Mapped[int] = mapped_column(Integer, nullable=False)
    first_line: Mapped[int] = mapped_column(Integer, nullable=False)
    last_line: Mapped[int] = mapped_column(Integer, nullable=False)
    asked: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt_ms: Mapped[int | None] = mapped_column(Integer)
    eval_ms: Mapped[int | None] = mapped_column(Integer)
    load_ms: Mapped[int | None] = mapped_column(Integer)
    total_ms: Mapped[int | None] = mapped_column(Integer)
    first_token_ms: Mapped[int | None] = mapped_column(Integer)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edited_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ignored_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reasoning: Mapped[str | None] = mapped_column(Text)
    prompt: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )


class OllamaSuggestion(Base):
    """The suggestion held for one line; NULL text means it was flushed (used or dismissed)."""

    __tablename__ = "ollama_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    line_id: Mapped[int] = mapped_column(
        ForeignKey("lines.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    chunk_id: Mapped[int] = mapped_column(
        ForeignKey("ollama_chunks.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str | None] = mapped_column(Text)
    raw_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    scored: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class OllamaQueueItem(Base):
    """A waiting run request; the worker takes them in `position` order."""

    __tablename__ = "ollama_queue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(10), nullable=False)  # series / volume / documents
    series_id: Mapped[int] = mapped_column(
        ForeignKey("series.id", ondelete="CASCADE"), nullable=False
    )
    volume_id: Mapped[int | None] = mapped_column(ForeignKey("volumes.id", ondelete="CASCADE"))
    # [] unless kind is "documents".
    document_ids: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=list)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
