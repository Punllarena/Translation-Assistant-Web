"""Jobs (spec §9): list, read, cancel, and follow one over SSE."""

import asyncio
import time

from fastapi import Depends
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.deps import current_user, db_session, scoped
from api.jobs import TERMINAL
from api.models import Job, User
from api.mt.base import sse
from api.routing import api_router
from api.schemas.jobs import JobOut

router = api_router(prefix="/jobs", tags=["jobs"])

POLL_SECONDS = 1.0
KEEPALIVE_SECONDS = 15.0  # an SSE comment so proxies keep an idle stream open


@router.get("", response_model=list[JobOut])
def list_jobs(
    active: bool = False,
    series_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[Job]:
    q = select(Job).where(Job.user_id == user.id)
    if active:
        q = q.where(Job.state.in_(("queued", "running")))
    if series_id is not None:
        q = q.where(Job.params_json["series_id"].as_integer() == series_id)
    return list(db.scalars(q.order_by(Job.id.desc()).limit(50)))


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Job:
    return scoped(db, Job, job_id, user.id)


@router.post("/{job_id}/cancel", response_model=JobOut)
def cancel_job(
    job_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Job:
    """A queued job is cancelled at once; a running one stops at its next progress
    point (the worker checks cancel_requested). Terminal jobs are left as they are."""
    scoped(db, Job, job_id, user.id)
    job = db.get(Job, job_id, with_for_update=True, populate_existing=True)
    if job.state == "queued":
        job.state, job.finished_at = "cancelled", func.now()
    elif job.state == "running":
        job.cancel_requested = True
    db.flush()
    return job


def _snapshot(job_id: int) -> dict:
    with SessionLocal() as s:
        job = s.get(Job, job_id, populate_existing=True)
        return JobOut.model_validate(job).model_dump(mode="json")


@router.get("/{job_id}/events")
async def job_events(
    job_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> StreamingResponse:
    await run_in_threadpool(scoped, db, Job, job_id, user.id)

    async def frames():
        last, sent_at = None, time.monotonic()
        while True:
            snap = await run_in_threadpool(_snapshot, job_id)
            if snap != last:
                yield sse(("job", snap))
                last, sent_at = snap, time.monotonic()
            elif time.monotonic() - sent_at >= KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                sent_at = time.monotonic()
            if snap["state"] in TERMINAL:
                return
            await asyncio.sleep(POLL_SECONDS)

    return StreamingResponse(
        frames(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
