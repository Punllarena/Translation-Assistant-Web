"""Ollama statistics (spec: Statistics): throughput, outcomes and per-model comparison,
read from ollama_chunks and finished ollama_run jobs."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.models import Job, OllamaChunk

WINDOW = timedelta(days=30)
RUN_LIMIT = 60
C = OllamaChunk


def _rate(tokens, ms) -> float | None:
    """Tokens per second from summed output tokens and eval milliseconds."""
    return tokens / ms * 1000 if ms else None


def _timed():
    """ok chunks carrying the numbers the tokens/s figure needs."""
    return C.ok & C.eval_ms.is_not(None) & C.output_tokens.is_not(None)


def _pct(used: int, edited: int, ignored: int) -> float | None:
    total = used + edited + ignored
    return (used + edited) / total * 100 if total else None


def summary(db: Session, user_id: int, now: datetime | None = None) -> dict:
    since = (now or datetime.now(UTC)) - WINDOW
    mine = (C.user_id == user_id, C.created_at >= since)
    tokens, ms = db.execute(
        select(func.coalesce(func.sum(C.output_tokens), 0), func.coalesce(func.sum(C.eval_ms), 0))
        .where(*mine, _timed())
    ).one()
    lines, chapters, used, edited, ignored, total, failed = db.execute(
        select(
            func.coalesce(func.sum(C.asked).filter(C.ok), 0),
            func.count(func.distinct(C.document_id)).filter(C.ok),
            func.coalesce(func.sum(C.used_count), 0),
            func.coalesce(func.sum(C.edited_count), 0),
            func.coalesce(func.sum(C.ignored_count), 0),
            func.count(C.id),
            func.count(C.id).filter(C.ok.is_(False)),
        ).where(*mine)
    ).one()
    return {
        "tokens_per_s_30d": _rate(tokens, ms), "lines_30d": lines, "chapters_30d": chapters,
        "outcomes": {"used": used, "edited": edited, "ignored": ignored},
        "retry_rate_30d": failed / total if total else None,
    }


def runs(db: Session, user_id: int, tz: ZoneInfo) -> list[dict]:
    jobs = db.scalars(
        select(Job).where(Job.user_id == user_id, Job.kind == "ollama_run",
                          Job.finished_at.is_not(None))
        .order_by(Job.finished_at.desc(), Job.id.desc()).limit(RUN_LIMIT)
    ).all()
    stats = {
        r.job_id: r for r in db.execute(
            select(
                C.job_id,
                func.count(func.distinct(C.document_id)).label("chapters"),
                func.coalesce(func.sum(C.output_tokens).filter(_timed()), 0).label("tokens"),
                func.coalesce(func.sum(C.eval_ms).filter(_timed()), 0).label("ms"),
                func.avg(C.total_ms).filter(C.ok).label("total_ms"),
            ).where(C.user_id == user_id, C.job_id.in_([j.id for j in jobs])).group_by(C.job_id)
        )
    }
    out = []
    for job in jobs:
        s = stats.get(job.id)
        lines = (job.result_json or {}).get("lines")
        lines = lines if isinstance(lines, int) else 0
        seconds = (job.finished_at - job.started_at).total_seconds() if job.started_at else None
        out.append({
            "job_id": job.id,
            "date": (job.finished_at or job.created_at).astimezone(tz).date().isoformat(),
            "chapters": s.chapters if s else 0,
            "lines": lines,
            "duration_s": seconds,
            "tokens_per_s": _rate(s.tokens, s.ms) if s else None,
            "lines_per_hour": lines / seconds * 3600 if seconds else None,
            "s_per_chunk": float(s.total_ms) / 1000 if s and s.total_ms is not None else None,
        })
    return out


def by_model(db: Session, user_id: int) -> list[dict]:
    rows = db.execute(
        select(
            C.model, C.preset, C.chunk_lines, C.context_lines,
            func.count(func.distinct(C.job_id)).label("runs"),
            func.coalesce(func.sum(C.output_tokens).filter(_timed()), 0).label("tok"),
            func.coalesce(func.sum(C.eval_ms).filter(_timed()), 0).label("ms"),
            func.coalesce(func.sum(C.prompt_tokens), 0).label("prompt"),
            func.coalesce(func.sum(C.output_tokens), 0).label("output"),
            func.avg(C.total_ms).filter(C.ok).label("total_ms"),
            func.coalesce(func.sum(C.used_count), 0).label("used"),
            func.coalesce(func.sum(C.edited_count), 0).label("edited"),
            func.coalesce(func.sum(C.ignored_count), 0).label("ignored"),
        ).where(C.user_id == user_id)
        .group_by(C.model, C.preset, C.chunk_lines, C.context_lines)
        .order_by(C.model, C.preset, C.chunk_lines, C.context_lines)
    ).all()
    return [{
        "model": r.model, "preset": r.preset, "chunk_lines": r.chunk_lines,
        "context_lines": r.context_lines, "runs": r.runs, "tokens_per_s": _rate(r.tok, r.ms),
        "prompt_tokens": r.prompt, "output_tokens": r.output,
        "s_per_chunk": float(r.total_ms) / 1000 if r.total_ms is not None else None,
        "used_or_edited_pct": _pct(r.used, r.edited, r.ignored),
    } for r in rows]
