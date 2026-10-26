"""Statistics (spec §10): the desktop StatsDialog's data, derived from lines.translated_at,
with days in the viewer's time zone (ruling 2)."""

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import Depends
from sqlalchemy import Date, case, cast, func, select, text
from sqlalchemy.orm import Session

from api.core import stats
from api.deps import current_user, db_session, zone
from api.models import Document, Line, Series, User
from api.ollama import stats as ollama_stats
from api.routing import api_router
from api.schemas.stats import OllamaStatsOut, StatsOut

router = api_router(tags=["stats"])


def _metrics():
    """paragraphs, source chars, and the desktop's _EN_WORDS (spaces + 1 per trimmed line)."""
    t = func.btrim(Line.translated_text)
    words = case((t != "", func.length(t) - func.length(func.replace(t, " ", "")) + 1), else_=0)
    return (func.count(Line.id), func.coalesce(func.sum(func.length(Line.raw_text)), 0),
            func.coalesce(func.sum(words), 0))


@router.get("/stats", response_model=StatsOut)
def get_stats(
    tz: ZoneInfo = Depends(zone), user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> StatsOut:
    # ponytail: a zone Python knows but Postgres doesn't would 500; both ship IANA data
    day = cast(func.timezone(tz.key, Line.translated_at), Date)
    mine = (Line.translated_at.is_not(None), Document.user_id == user.id)
    rows = db.execute(
        select(day, *_metrics()).join(Document, Document.id == Line.document_id)
        .where(*mine).group_by(text("1")).order_by(text("1"))  # positional: the zone is a bind
    ).all()
    history = [{"date": d.isoformat(), "paragraphs": p, "chars": c, "en_words": w}
               for d, p, c, w in rows]
    today = datetime.now(tz).date()
    by_series = db.execute(
        select(Series.id, Series.title, *_metrics(), func.count(func.distinct(Line.document_id)))
        .join(Document, Document.id == Line.document_id)
        .join(Series, Series.id == Document.series_id)
        .where(*mine).group_by(Series.id, Series.title).order_by(func.count(Line.id).desc())
    ).all()
    return StatsOut(
        today=today, daily=history, summary=stats.summarize(history, today),
        streaks=stats.compute_streaks(history, today),
        comparisons={m: stats.compute_period_comparisons(history, m, today) for m in stats.METRICS},
        series=[{"series_id": i, "series": t, "paragraphs": p, "chars": c, "en_words": w,
                 "chapters": n} for i, t, p, c, w, n in by_series],
    )


@router.get("/stats/ollama", response_model=OllamaStatsOut)
def get_ollama_stats(
    tz: ZoneInfo = Depends(zone), user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> OllamaStatsOut:
    return OllamaStatsOut(
        **ollama_stats.summary(db, user.id), runs=ollama_stats.runs(db, user.id, tz),
        by_model=ollama_stats.by_model(db, user.id),
    )
