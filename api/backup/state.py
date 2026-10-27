"""The restore's in-memory state and the admission gate around it.

A restore replaces the ``jobs`` table and the users who own jobs, so it cannot be a job. It
runs in a background thread and this module holds its status, while every out-of-request
writer (the job worker, the Ollama runner and scheduler tick, a by-hand chunk, an
``/mt/stream`` translation) enters :func:`work` before it starts. A restore turns
maintenance on under the same lock as that count, so nothing can slip in between its check
and the switch.

# ponytail: in-process and single replica, like the job worker (api/jobs.py) and the Ollama
# lane (api/ollama/lane.py). Two API processes would each need their own gate row in Postgres.
"""

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import Job

BUSY = "A job or translation is running; cancel it or wait, then try again."
RESTORING = "A restore is already in progress."
IN_PROGRESS = "Restore in progress"  # the 503 detail, and the stream error while one runs
ACTIVE_STATES = ("queued", "running")
Phase = Literal["idle", "restoring", "done", "failed"]


@dataclass(frozen=True)
class Status:
    phase: Phase = "idle"
    done: int = 0
    total: int = 0
    message: str = ""
    error: str | None = None


class Maintenance(Exception):
    """A restore is running: this work must not start."""


_lock = threading.Lock()
_status = Status()
_in_flight = 0


def snapshot() -> Status:
    with _lock:
        return _status


def active() -> bool:
    return snapshot().phase == "restoring"


@contextmanager
def work() -> Iterator[None]:
    """Count one unit of out-of-request work until the block exits."""
    global _in_flight
    with _lock:
        if _status.phase == "restoring":
            raise Maintenance()
        _in_flight += 1
    try:
        yield
    finally:
        with _lock:
            _in_flight -= 1


def busy(db: Session) -> bool:
    """Would ``try_begin`` refuse? (The router's cheap pre-check, before the upload.)"""
    with _lock:
        if _in_flight:
            return True
    return db.scalar(select(Job.id).where(Job.state.in_(ACTIVE_STATES)).limit(1)) is not None


def try_begin(db: Session) -> str | None:
    """Turn maintenance on unless work is in flight or a job is queued or running.

    Returns BUSY or RESTORING instead. The phase check stops two uploads that both passed the
    router's early answer from both starting.
    """
    global _status
    with _lock:
        if _status.phase == "restoring":
            return RESTORING
        if _in_flight:
            return BUSY
        if db.scalar(select(Job.id).where(Job.state.in_(ACTIVE_STATES)).limit(1)) is not None:
            return BUSY
        _status = Status(phase="restoring")
        return None


def progress(done: int, total: int, message: str) -> None:
    global _status
    with _lock:
        if _status.phase == "restoring":
            _status = Status(phase="restoring", done=done, total=total, message=message)


def finish(error: str | None = None) -> None:
    """The database committed; ``error`` is a warning shown with the success message."""
    global _status
    with _lock:
        current = _status
        _status = Status(phase="done", done=current.done, total=current.total,
                         message=current.message, error=error)


def fail(error: str) -> None:
    """Nothing was changed: the restore stopped before the commit."""
    global _status
    with _lock:
        _status = Status(phase="failed", error=error)


def reset() -> None:
    """Tests only: a restore left in one test must not reach the next."""
    global _status, _in_flight
    with _lock:
        _status = Status()
        _in_flight = 0
