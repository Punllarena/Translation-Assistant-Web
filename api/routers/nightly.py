"""The nightly syosetu check's recent runs, per series, for the Library badges.

ponytail: the ``jobs`` rows are the store (finished history is kept and backed up); no
table of its own. Only series that got new chapters or failed are listed in a run."""

from datetime import datetime

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import current_user, db_session
from api.models import Job, User
from api.routing import api_router

router = api_router(prefix="/syosetu/nightly", tags=["syosetu"])


class NightlySeries(BaseModel):
    series_id: int
    new_chapters: int
    error: str | None


class NightlyRun(BaseModel):
    job_id: int
    finished_at: datetime | None
    series: list[NightlySeries]


def per_series(result: dict | None) -> list[NightlySeries]:
    r = result or {}
    return [NightlySeries(series_id=q["series_id"], new_chapters=q["chapters"], error=None)
            for q in r.get("queued", [])] + \
           [NightlySeries(series_id=f["series_id"], new_chapters=0, error=f["message"])
            for f in r.get("failed", [])]


@router.get("/runs", response_model=list[NightlyRun])
def runs(
    limit: int = Query(5, ge=1, le=50),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[NightlyRun]:
    """The caller's last finished nightly runs, newest first."""
    rows = db.scalars(
        select(Job).where(Job.user_id == user.id, Job.kind == "syosetu_nightly",
                          Job.state == "done")
        .order_by(Job.id.desc()).limit(limit))
    return [NightlyRun(job_id=j.id, finished_at=j.finished_at, series=per_series(j.result_json))
            for j in rows]
