"""Per-user night windows for Ollama runs, and the once-a-minute tick that starts them (spec §6)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi.concurrency import run_in_threadpool
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api import jobs
from api.db import SessionLocal
from api.models import Job, UserSetting
from api.models.ollama import OllamaChunk, OllamaQueueItem, OllamaSuggestion

log = logging.getLogger(__name__)

KEY = "ollama_schedule"


@dataclass(frozen=True)
class Schedule:
    enabled: bool
    start: time
    end: time
    days: frozenset[int]  # 0 = Monday, the local day the window starts
    tz: str


def _time(value: Any) -> time:
    return time.fromisoformat(value) if isinstance(value, str) and len(value) == 5 else _bad()


def _bad():
    raise ValueError("bad time")


def parse(value: Any) -> Schedule | None:
    """The stored setting as a Schedule; None when it is missing or invalid."""
    if not isinstance(value, dict):
        return None
    try:
        tz = value["tz"]
        ZoneInfo(tz)
        days = frozenset(int(d) for d in value["days"])
        if not days <= set(range(7)):
            return None
        return Schedule(bool(value["enabled"]), _time(value["start"]), _time(value["end"]),
                        days, tz)
    except (KeyError, TypeError, ValueError, OSError):  # ZoneInfoNotFoundError is a KeyError
        return None


def window_at(s: Schedule, now: datetime) -> tuple[str, datetime] | None:
    """The window open at ``now``: its key (local start, ISO) and its end in UTC."""
    zone = ZoneInfo(s.tz)
    today = now.astimezone(zone).date()
    for day in (today, today - timedelta(days=1)):
        if day.weekday() not in s.days:
            continue
        start = datetime.combine(day, s.start, zone)
        end_day = day if s.end > s.start else day + timedelta(days=1)
        end = datetime.combine(end_day, s.end, zone).astimezone(UTC)
        if start.astimezone(UTC) <= now < end:
            return start.replace(tzinfo=None).isoformat(), end
    return None


def _start_run(db: Session, user_id: int, key: str, until: datetime) -> None:
    """One run per window; a run a server restart interrupted does not count, so the window
    goes on after the restart (the unique index still stops a second active run)."""
    exists_already = db.scalar(
        select(exists().where(
            Job.user_id == user_id, Job.kind == "ollama_run",
            Job.params_json["window"].astext == key,
            ~((Job.state == "failed") & (Job.message == jobs.INTERRUPTED)),
        ))
    )
    if exists_already:
        return
    try:
        with db.begin_nested():  # a unique-index hit must not poison the session
            jobs.enqueue(db, user_id, "ollama_run", {"window": key, "until": until.isoformat()})
    except IntegrityError:
        pass  # a run is already active for this user


def _cleanup_users(db: Session, now: datetime) -> list[int]:
    """Users with unflushed suggestions and no clean-up job yet on this UTC day."""
    day = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    queued_today = select(Job.user_id).where(
        Job.kind == "ollama_cleanup",
        Job.created_at >= day,
        Job.created_at < day + timedelta(days=1),
    )
    return list(db.scalars(
        select(OllamaChunk.user_id)
        .join(OllamaSuggestion, OllamaSuggestion.chunk_id == OllamaChunk.id)
        .where(OllamaSuggestion.text.is_not(None), OllamaChunk.user_id.not_in(queued_today))
        .distinct()
    ))


def tick(db: Session, now: datetime) -> None:
    """Start a night run for every user whose window is open and whose queue is not empty,
    and queue the daily clean-up. Commits its own session (a sanctioned commit outside the
    route boundary, like the job worker's)."""
    for setting in db.scalars(select(UserSetting).where(UserSetting.key == KEY)):
        s = parse(setting.value_json)
        if s is None or not s.enabled:
            continue
        opened = window_at(s, now)
        if opened is None:
            continue
        has_queue = db.scalar(
            select(exists().where(OllamaQueueItem.user_id == setting.user_id))
        )
        if has_queue:
            _start_run(db, setting.user_id, *opened)
    for user_id in _cleanup_users(db, now):
        job = jobs.enqueue(db, user_id, "ollama_cleanup", {})
        job.created_at = now  # the once-a-day check reads this
    db.commit()


def _tick_once() -> None:
    with SessionLocal() as db:
        tick(db, datetime.now(UTC))


async def ticker(stop: asyncio.Event, every: float = 60.0) -> None:
    """Run ``tick`` every ``every`` seconds until ``stop`` is set; a failed tick is logged."""
    while not stop.is_set():
        try:
            await run_in_threadpool(_tick_once)
        except Exception:
            log.exception("ollama schedule tick failed")
        try:
            await asyncio.wait_for(stop.wait(), every)
        except TimeoutError:
            pass
