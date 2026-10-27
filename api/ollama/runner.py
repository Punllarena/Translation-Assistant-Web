"""The Ollama runner (spec "Running Ollama off the main job worker").

It claims ``ollama_run`` jobs, which the general worker skips (``jobs.SEPARATE_KINDS``), and works
through the user's queue one chunk at a time, every request through the user's lane so by-hand
requests go first. Up to MAX_RUNS users run at once (the unique index allows one run per user).
Nothing is kept about where a run stopped: each chunk is derived from the queue afresh.

Each chunk's save is committed with the job's progress in the runner's own session; those, the
claim and the final job update are sanctioned commits outside the request boundary (CLAUDE.md),
like the job worker's.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api import jobs
from api.backup import state
from api.db import SessionLocal
from api.models import Document, Job
from api.mt.base import BackendError
from api.ollama import endpoint
from api.ollama.lane import LANES
from api.ollama.prefs import OllamaPrefs
from api.ollama.prompt import steady_ctx
from api.ollama.translate import ChunkResult, Endpoint, translate
from api.ollama.work import Plan, next_plan, save

log = logging.getLogger(__name__)

KIND = "ollama_run"
MAX_RUNS = 4  # users translating at once, server-wide
RETRIES = 3
PAUSES = (30, 120, 300)  # seconds before each retry of a chunk the server did not answer
PAUSE_STEP = 5.0  # a cancel or window end is noticed this often during a pause
_GONE = "gone"  # the job row vanished (its user was deleted)
_INTERRUPTED = "interrupted"  # the server is shutting down


def _now() -> datetime:
    return datetime.now(UTC)


def http_client() -> httpx.AsyncClient:
    """The seam tests replace with an httpx.MockTransport client."""
    return httpx.AsyncClient()  # follow_redirects stays False: a redirect is no SSRF bypass


class _Failed(Exception):
    """The run cannot go on; the message is stored on the job."""


@dataclass
class _Tally:
    lines: int = 0
    failed: int = 0
    chunks: int = 0
    retries: int = 0
    clamped: int = 0

    def result(self, reason: str) -> dict:
        return {**asdict(self), "reason": reason}


@dataclass
class _Step:
    user_id: int
    plan: Plan
    p: OllamaPrefs
    ep: Endpoint


def claim(db: Session) -> Job | None:
    """The oldest queued run, now running (committed)."""
    job = db.scalar(
        select(Job)
        .where(Job.state == "queued", Job.kind == KIND)
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is not None:
        job.state, job.started_at = "running", _now()
        db.commit()
    return job


def _passed(until: object) -> bool:
    if not isinstance(until, str):
        return False
    try:
        end = datetime.fromisoformat(until)
    except ValueError:
        return False
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    return end <= _now()


def _stop_reason(job: Job | None) -> str | None:
    if job is None:
        return _GONE
    if jobs.stopping.is_set():
        return _INTERRUPTED
    if job.cancel_requested:
        return "cancelled"
    if _passed((job.params_json or {}).get("until")):
        return "window closed"
    return None


def _check(job_id: int) -> str | None:
    with SessionLocal() as db:
        return _stop_reason(db.get(Job, job_id, populate_existing=True))


def _next(job_id: int, skip: frozenset[int]) -> _Step | str:
    """The next chunk to ask, or why the run ends."""
    with SessionLocal() as db:
        job = db.get(Job, job_id, populate_existing=True)
        reason = _stop_reason(job)
        if reason:
            return reason
        assert job is not None
        user_id = job.user_id
        p = endpoint.prefs_for(db, user_id)
        plan = next_plan(db, user_id, p, skip)
        db.commit()  # volume and chapter items with nothing left leave the queue
        if plan is None:
            return "finished"
        ep, problem = endpoint.load(db, user_id)
        if ep is None:
            raise _Failed(problem or "Ollama is not set up")
        doc = db.get(Document, plan.document_id)
        src = (doc.source_language if doc else None) or "ja"
        return _Step(user_id, plan, p, replace(ep, src=src))


def _recheck(url: str) -> str | None:
    with SessionLocal() as db:
        return endpoint.recheck(db, url)


def _save(job_id: int, step: _Step, result: ChunkResult, done: int) -> None:
    with SessionLocal() as db:
        save(db, step.user_id, step.plan, result.requests, result.lines, source="run",
             job_id=job_id, p=step.p, model=step.ep.model)
        db.execute(update(Job).where(Job.id == job_id).values(progress=done))
        db.commit()


def _finish(job_id: int, state: str, message: str, result: dict) -> None:
    with SessionLocal() as db:
        job = db.get(Job, job_id, populate_existing=True)
        if job is None:
            return
        job.state, job.message, job.result_json = state, message, result
        job.finished_at = _now()
        db.commit()


async def _pause(job_id: int, seconds: float) -> str | None:
    left = seconds
    while left > 0:
        step = min(left, PAUSE_STEP)
        await asyncio.sleep(step)
        left -= step
        reason = await run_in_threadpool(_check, job_id)
        if reason:
            return reason
    return None


async def _chunk(
    job_id: int, client: httpx.AsyncClient, step: _Step, tally: _Tally,
    saved: Callable[[ChunkResult], Awaitable[None]], ctx: int,
) -> ChunkResult | str:
    """Translate one chunk through the lane; retry an unanswered server after a pause. The
    result is saved before the lane is released, so a by-hand request waiting behind this
    chunk rereads committed rows."""
    for attempt in range(RETRIES + 1):
        try:
            async with LANES.hold(step.user_id, priority=False):
                problem = await run_in_threadpool(_recheck, step.ep.url)
                if problem:
                    raise _Failed(problem)
                ep = await endpoint.ready(client, step.ep)

                async def should_stop() -> bool:  # a halving cascade ends on cancel or window end
                    return await run_in_threadpool(_check, job_id) is not None

                result = await translate(client, ep, step.plan.before, step.plan.chunk, ctx=ctx,
                                         should_stop=should_stop)
                await saved(result)
                return result
        except BackendError as exc:
            if attempt == RETRIES:
                raise _Failed(str(exc)) from exc
            log.warning("ollama run %s: %s; retrying", job_id, exc)
        tally.retries += 1
        reason = await _pause(job_id, PAUSES[attempt])
        if reason:
            return reason
    raise AssertionError("unreachable")


async def _work(job_id: int, factory: Callable[[], httpx.AsyncClient], tally: _Tally) -> str:
    # lines asked in this run and not answered (failed, or left unasked by a stop) are not
    # asked again, so no chunk can be asked forever
    skip: set[int] = set()
    window = 0  # the largest num_ctx sent in this run: it never steps down (no model reload)
    async with factory() as client:
        while True:
            step = await run_in_threadpool(_next, job_id, frozenset(skip))
            if isinstance(step, str):
                return step
            ctx = max(window, steady_ctx(step.ep.system_prompt, step.p.chunk_lines,
                                         step.p.context_lines))

            async def saved(result: ChunkResult, step: _Step = step) -> None:
                skip.update(r.line_id for r in step.plan.asked if r.line_number not in result.lines)
                tally.chunks += 1
                tally.lines += len(result.lines)
                tally.failed += len(result.failed)
                tally.clamped += sum(1 for r in result.requests if r.clamped)
                await run_in_threadpool(_save, job_id, step, result, tally.lines)

            result = await _chunk(job_id, client, step, tally, saved, ctx)
            if isinstance(result, str):
                return result
            window = max(ctx, result.num_ctx)


async def run_one(
    job_id: int, client_factory: Callable[[], httpx.AsyncClient] | None = None
) -> None:
    """Run a claimed job until its work, window or user says stop. Never raises, except the
    cancellation the runner uses at shutdown (the job is marked interrupted first)."""
    tally = _Tally()
    state, message = "done", ""
    cancelled = False
    try:
        reason = await _work(job_id, client_factory or http_client, tally)
    except _Failed as exc:
        state, message, reason = "failed", str(exc), "server unreachable"
    except asyncio.CancelledError:
        reason, cancelled = _INTERRUPTED, True
    except Exception:
        log.exception("ollama run %s failed", job_id)
        state, message, reason = "failed", f"{KIND} failed", "server unreachable"
    if reason == _GONE:
        return
    if reason == _INTERRUPTED:
        state, message, reason = "failed", jobs.INTERRUPTED, "cancelled"
    elif reason == "cancelled":
        state = "cancelled"
    try:
        await run_in_threadpool(_finish, job_id, state, message, tally.result(reason))
    except Exception:
        log.exception("ollama run %s: recording the result failed", job_id)
    if cancelled:
        raise asyncio.CancelledError


def _claim_id() -> int | None:
    if state.active():  # a restore is replacing the jobs table: claim nothing
        return None
    with SessionLocal() as db:
        job = claim(db)
        return None if job is None else job.id


async def _gated(job_id: int) -> None:
    """One claimed run, counted as work in flight. A restore that begins first wins."""
    try:
        with state.work():
            await run_one(job_id)
    except state.Maintenance:
        # The claim landed just as a restore began. Its jobs table is being replaced, so there
        # is nothing worth writing; if the restore fails the row stays running until the next
        # restart marks it interrupted, as a crash would.
        log.warning("ollama run %s was not started: a restore is in progress", job_id)


async def runner(stop: asyncio.Event, max_runs: int = MAX_RUNS, idle: float = 1.0) -> None:
    """Claim queued runs, up to ``max_runs`` at once, until ``stop`` is set. At shutdown the
    runs in flight are cancelled; chunks already saved stay."""
    tasks: set[asyncio.Task] = set()
    try:
        while not stop.is_set():
            while len(tasks) < max_runs:
                try:
                    job_id = await run_in_threadpool(_claim_id)
                except Exception:
                    log.exception("ollama runner claim failed")
                    break
                if job_id is None:
                    break
                task = asyncio.create_task(_gated(job_id))
                tasks.add(task)
                task.add_done_callback(tasks.discard)
            try:
                await asyncio.wait_for(stop.wait(), idle)
            except TimeoutError:
                pass
    finally:
        pending = list(tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
