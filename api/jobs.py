"""The jobs table driver and the in-process worker (spec §9).

One asyncio task, started in the app lifespan, runs one job at a time in the
threadpool. A handler gets a JobContext: its own session (committed at each
progress point, so the work so far and the progress land together) and the job row.
This and the /mt/stream cache write are the only commits outside the request
boundary (CLAUDE.md).

# ponytail: in-process worker, single replica. Swap for arq + Redis when the
# deployment needs more than one API container (spec §9).
"""

import asyncio
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import Job

log = logging.getLogger(__name__)

TERMINAL = {"done", "failed", "cancelled"}
INTERRUPTED = "interrupted by a server restart; start it again to resume"
HANDLERS: dict[str, Callable[["JobContext"], dict]] = {}
stopping = threading.Event()  # set by the lifespan on shutdown


class JobError(Exception):
    """A failure the user should read (the message is stored on the job)."""


class Cancelled(Exception):
    """The user cancelled the job; work committed before this point stays."""


class _Interrupted(Exception):
    """The server is shutting down."""


def handler(kind: str):
    def register(fn: Callable[["JobContext"], dict]):
        HANDLERS[kind] = fn
        return fn
    return register


class JobContext:
    def __init__(self, db: Session, job: Job) -> None:
        self.db = db
        self.job = job

    @property
    def params(self) -> dict:
        return self.job.params_json

    def progress(self, done: int, total: int, message: str = "") -> None:
        """Commit the work so far with the progress, then stop if asked to."""
        self.job.progress, self.job.total, self.job.message = done, total, message
        self.db.commit()
        self.db.refresh(self.job)  # sees cancel_requested set by another session
        if stopping.is_set():
            raise _Interrupted
        if self.job.cancel_requested:
            raise Cancelled


def _now() -> datetime:
    return datetime.now(UTC)


def enqueue(db: Session, user_id: int, kind: str, params: dict, total: int = 0) -> Job:
    """Queue a job in the request's session (the route commits it)."""
    job = Job(user_id=user_id, kind=kind, params_json=params, total=total)
    db.add(job)
    db.flush()
    return job


def _claim(db: Session) -> Job | None:
    job = db.scalar(
        select(Job)
        .where(Job.state == "queued")
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is not None:
        job.state, job.started_at = "running", _now()
        db.commit()
    return job


def run_next() -> bool:
    """Run the oldest queued job to completion. False when there was none."""
    with SessionLocal() as db:
        job = _claim(db)
        if job is None:
            return False
        fn = HANDLERS.get(job.kind)
        try:
            if fn is None:
                raise JobError(f"unknown job kind {job.kind!r}")
            result = fn(JobContext(db, job))
            job.state, job.result_json = "done", result or {}
        except Cancelled:
            db.rollback()
            job.state = "cancelled"
        except _Interrupted:
            db.rollback()
            job.state, job.message = "failed", INTERRUPTED
        except JobError as exc:
            db.rollback()
            job.state, job.message = "failed", str(exc)
        except Exception:
            log.exception("job %s (%s) failed", job.id, job.kind)
            db.rollback()
            job.state, job.message = "failed", f"{job.kind} failed"
        job.finished_at = _now()
        db.commit()
        return True


def fail_interrupted() -> int:
    """At startup: a job still marked running died with the previous process."""
    with SessionLocal() as db:
        n = db.execute(
            update(Job)
            .where(Job.state == "running")
            .values(state="failed", message=INTERRUPTED, finished_at=_now())
        ).rowcount
        db.commit()
        return n


async def worker(stop: asyncio.Event, idle: float = 1.0) -> None:
    """Poll for queued jobs until ``stop`` is set."""
    while not stop.is_set():
        try:
            ran = await run_in_threadpool(run_next)
        except Exception:
            log.exception("job worker iteration failed")
            ran = False
        if not ran:
            try:
                await asyncio.wait_for(stop.wait(), idle)
            except TimeoutError:
                pass
