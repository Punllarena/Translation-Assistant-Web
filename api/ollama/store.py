"""Held suggestions: flush them, clean up old ones, and score how they fared (spec §5).

Flushing clears only the text-bearing columns (`ollama_suggestions.text`, the chunks'
`reasoning` and `prompt`); chunk rows and their stats stay, and the queue is never touched.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from api.jobs import JobContext, handler
from api.models import Document, Line
from api.models.ollama import OllamaChunk, OllamaSuggestion
from api.ollama.outcome import score

RETENTION = timedelta(days=91)  # "three months"; dateutil is not a dependency
_COUNTERS = {"used": "used_count", "edited": "edited_count", "ignored": "ignored_count"}


def flush(
    db: Session,
    user_id: int,
    *,
    document_ids: list[int] | None = None,
    volume_id: int | None = None,
    series_id: int | None = None,
) -> int:
    """Drop held suggestion text (and the affected chunks' reasoning and prompt). With no
    scope given it covers everything of the user's; returns the suggestions cleared."""
    docs = select(Document.id).where(Document.user_id == user_id)
    if document_ids is not None:
        docs = docs.where(Document.id.in_(document_ids))
    if volume_id is not None:
        docs = docs.where(Document.volume_id == volume_id)
    if series_id is not None:
        docs = docs.where(Document.series_id == series_id)
    held = (
        select(OllamaSuggestion.id, OllamaSuggestion.chunk_id)
        .join(Line, Line.id == OllamaSuggestion.line_id)
        .where(Line.document_id.in_(docs), OllamaSuggestion.text.is_not(None))
    ).subquery()
    chunk_ids = set(db.scalars(select(held.c.chunk_id))) | set(
        db.scalars(select(OllamaChunk.id).where(
            OllamaChunk.user_id == user_id, OllamaChunk.document_id.in_(docs)
        ))
    )
    cleared = db.execute(
        update(OllamaSuggestion)
        .where(OllamaSuggestion.id.in_(select(held.c.id)))
        .values(text=None)
    ).rowcount
    if chunk_ids:
        db.execute(
            update(OllamaChunk)
            .where(OllamaChunk.id.in_(chunk_ids), OllamaChunk.user_id == user_id)
            .values(reasoning=None, prompt=None)
        )
    return cleared


def cleanup(db: Session, user_id: int, now: datetime) -> int:
    """Flush the suggestions of chapters that are fully translated and untouched for three
    months; returns the chapters cleared."""
    candidates = (
        select(Line.document_id)
        .join(OllamaSuggestion, OllamaSuggestion.line_id == Line.id)
        .join(Document, Document.id == Line.document_id)
        .where(Document.user_id == user_id, OllamaSuggestion.text.is_not(None))
        .distinct()
    )
    untranslated = (
        func.btrim(Line.raw_text) != ""
    ) & (Line.translated_text == "")
    done = db.scalars(
        select(Line.document_id)
        .where(Line.document_id.in_(candidates))
        .group_by(Line.document_id)
        .having(
            func.count().filter(untranslated) == 0,
            func.max(Line.translated_at) < now - RETENTION,
        )
    ).all()
    if done:
        flush(db, user_id, document_ids=list(done))
    return len(done)


def record_outcomes(db: Session, document_id: int, saved: dict[int, str]) -> None:
    """Score each saved line against its unscored, unflushed suggestion, once."""
    wanted = {n: t for n, t in saved.items() if t}
    if not wanted:
        return
    rows = db.execute(
        select(OllamaSuggestion, Line.line_number)
        .join(Line, Line.id == OllamaSuggestion.line_id)
        .where(
            Line.document_id == document_id,
            Line.line_number.in_(wanted),
            OllamaSuggestion.scored.is_(False),
            OllamaSuggestion.text.is_not(None),
        )
    ).all()
    if not rows:
        return
    chunks = {
        c.id: c
        for c in db.scalars(select(OllamaChunk).where(
            OllamaChunk.id.in_({s.chunk_id for s, _ in rows})))
    }
    for suggestion, number in rows:
        verdict, _ = score(suggestion.text, wanted[number])
        chunk = chunks[suggestion.chunk_id]
        attr = _COUNTERS[verdict]
        setattr(chunk, attr, getattr(chunk, attr) + 1)
        suggestion.scored = True
    db.flush()


@handler("ollama_cleanup")
def cleanup_job(ctx: JobContext) -> dict:
    return {"chapters": cleanup(ctx.db, ctx.job.user_id, datetime.now(UTC))}
