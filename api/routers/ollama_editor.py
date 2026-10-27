"""Ollama in the editor (spec "The editor"): a chapter's held suggestions, one chunk's detail,
and by-hand translation of the chunk a line belongs to (SSE).

A by-hand chunk runs in a server-owned task (`_start`), not in the SSE stream: the stream only
subscribes, so a client that disconnects (the card moving to the next line, say) leaves the
chunk running to its save, and a request for another line of the same chunk follows it instead
of asking again. The task goes through the user's lane ahead of a run's chunks (priority) but
never cuts the chunk in flight, and saves while it still holds the lane, so a request waiting
behind it rereads committed rows and reuses them. The save runs in its own session and commits,
a sanctioned commit outside the route boundary like the /mt/stream cache write (CLAUDE.md).
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass, replace

import httpx
from fastapi import Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.backup import state
from api.db import SessionLocal
from api.deps import current_user, db_session, scoped
from api.models import Document, Line, User
from api.models.ollama import OllamaChunk, OllamaSuggestion
from api.mt.base import BackendError, Event, sse
from api.ollama import endpoint
from api.ollama.lane import LANES
from api.ollama.prefs import OllamaPrefs
from api.ollama.prompt import steady_ctx
from api.ollama.translate import ChunkResult, Endpoint, translate
from api.ollama.work import Plan, plan_for_line, raw_sha, save
from api.routing import api_router
from api.schemas.ollama import ChunkOut, SuggestionOut

router = api_router(tags=["ollama"])
log = logging.getLogger(__name__)


def http_client() -> httpx.AsyncClient:
    """The seam tests replace with an httpx.MockTransport client."""
    return httpx.AsyncClient()  # follow_redirects stays False: a redirect is no SSRF bypass


@router.get("/documents/{document_id}/ollama", response_model=list[SuggestionOut])
def suggestions(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[SuggestionOut]:
    """The chapter's unflushed suggestions, in line order."""
    doc = scoped(db, Document, document_id, user.id)
    rows = db.execute(
        select(Line.line_number, Line.raw_text, OllamaSuggestion, OllamaChunk)
        .join(OllamaSuggestion, OllamaSuggestion.line_id == Line.id)
        .join(OllamaChunk, OllamaChunk.id == OllamaSuggestion.chunk_id)
        .where(Line.document_id == doc.id, OllamaSuggestion.text.is_not(None))
        .order_by(Line.line_number)
    )
    return [
        SuggestionOut(
            line_number=number, text=sug.text, stale=raw_sha(raw) != sug.raw_sha,
            chunk_id=chunk.id, first_line=chunk.first_line, last_line=chunk.last_line,
            model=chunk.model, created_at=chunk.created_at,  # a replaced suggestion keeps its row
        )
        for number, raw, sug, chunk in rows
    ]


@router.get("/ollama/chunks/{chunk_id}", response_model=ChunkOut)
def chunk_detail(
    chunk_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> ChunkOut:
    return ChunkOut.model_validate(scoped(db, OllamaChunk, chunk_id, user.id))


@dataclass
class _Prepared:
    user_id: int
    document_id: int
    line_number: int
    reroll: bool
    prefs: OllamaPrefs
    plan: Plan | None  # None: the line has no text to translate
    ep: Endpoint | None = None
    setup: str | None = None


@dataclass
class _Fresh:
    """The state once the lane is ours: a plan to ask, or lines to show without asking."""

    plan: Plan | None = None
    reused: list[tuple[int, str]] | None = None
    setup: str | None = None


def _prepare(
    db: Session, user_id: int, document_id: int, line_number: int, reroll: bool
) -> _Prepared:
    """The request's reads, before streaming. Blocking (DNS, decryption)."""
    doc = scoped(db, Document, document_id, user_id)
    line = db.scalar(
        select(Line.id).where(Line.document_id == doc.id, Line.line_number == line_number)
    )
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    p = endpoint.prefs_for(db, user_id)
    try:
        plan = plan_for_line(db, user_id, doc, line_number, p, reroll=reroll)
    except ValueError:  # blank line or an illustrations chapter
        return _Prepared(user_id, doc.id, line_number, reroll, p, None)
    ep, setup = endpoint.load(db, user_id)
    if ep is not None:
        ep = replace(ep, src=doc.source_language or "ja")
    return _Prepared(user_id, doc.id, line_number, reroll, p, plan, ep, setup)


def _reused(db: Session, plan: Plan) -> list[tuple[int, str]] | None:
    """The asked lines' current suggestions when every one is answered (or translated since)."""
    asked = [r.line_id for r in plan.asked]
    rows = db.execute(
        select(Line.line_number, Line.raw_text, Line.translated_text, OllamaSuggestion.text,
               OllamaSuggestion.raw_sha)
        .outerjoin(OllamaSuggestion, OllamaSuggestion.line_id == Line.id)
        .where(Line.id.in_(asked))
        .order_by(Line.line_number)
    ).all()
    if len(rows) != len(asked):
        return None
    out = []
    for number, raw, translated, text, sha in rows:
        if text is not None and sha == raw_sha(raw):
            out.append((number, text))
        elif not translated:
            return None
    return out


def _reread(prep: _Prepared) -> _Fresh:
    """After the wait for the lane: the URL guard again, then reuse or a fresh plan."""
    assert prep.plan is not None and prep.ep is not None
    with SessionLocal() as db:
        problem = endpoint.recheck(db, prep.ep.url)
        if problem:
            return _Fresh(setup=problem)
        if not prep.reroll:
            reused = _reused(db, prep.plan)
            if reused is not None:
                return _Fresh(reused=reused)
        doc = db.get(Document, prep.document_id)
        if doc is None or doc.user_id != prep.user_id:
            return _Fresh(reused=[])  # the chapter is gone: nothing left to do
        try:
            plan = plan_for_line(db, prep.user_id, doc, prep.line_number, prep.prefs,
                                 reroll=prep.reroll)
        except ValueError:
            return _Fresh(reused=[])
        return _Fresh(plan=plan)


def _save(prep: _Prepared, plan: Plan, result: ChunkResult) -> list[int]:
    assert prep.ep is not None
    # Sanctioned commit in its own session: this runs in a server-owned task, not a request.
    with SessionLocal() as db:
        ids = save(db, prep.user_id, plan, result.requests, result.lines,
                   source="reroll" if prep.reroll else "manual", job_id=None, p=prep.prefs,
                   model=prep.ep.model)
        db.commit()
        return ids


class _Chunk:
    """A by-hand chunk in flight. It belongs to the server, not to a stream: a subscriber
    replays the events so far and then follows live; leaving only unsubscribes."""

    def __init__(self) -> None:
        self.events: list[Event] = []
        self.subscribers: set[asyncio.Queue[Event | None]] = set()
        self.finished = False

    def emit(self, event: Event) -> None:
        self.events.append(event)
        for queue in self.subscribers:
            queue.put_nowait(event)

    def finish(self) -> None:
        self.finished = True
        for queue in self.subscribers:
            queue.put_nowait(None)

    async def follow(self) -> AsyncIterator[Event]:
        queue: asyncio.Queue[Event | None] = asyncio.Queue()
        for event in self.events:
            queue.put_nowait(event)
        if self.finished:
            queue.put_nowait(None)
        else:
            self.subscribers.add(queue)
        try:
            while (event := await queue.get()) is not None:
                yield event
        finally:
            self.subscribers.discard(queue)


_Key = tuple[int, int, int, int, bool]  # user, document, first line, last line, reroll
# The by-hand chunks in flight. In-process, like the lane (api/ollama/lane.py): the app is a
# single API process.
_RUNNING: dict[_Key, _Chunk] = {}
_TASKS: set[asyncio.Task] = set()  # strong references until each task ends


def _key(prep: _Prepared, reroll: bool) -> _Key:
    assert prep.plan is not None
    chunk = prep.plan.chunk
    return (prep.user_id, prep.document_id, chunk[0].line_number, chunk[-1].line_number, reroll)


async def _translate(
    chunk: _Chunk, client: httpx.AsyncClient, ep: Endpoint, plan: Plan, ctx: int
) -> ChunkResult:
    """translate() with its line and thinking callbacks emitted as events."""
    sent: dict[int, str] = {}

    async def on_line(number: int, text: str) -> None:
        sent[number] = text
        chunk.emit(("line", {"line_number": number, "text": text}))

    async def on_thinking(text: str) -> None:
        chunk.emit(("thinking", {"text": text}))

    result = await translate(client, ep, plan.before, plan.chunk, ctx=ctx,
                             on_line=on_line, on_thinking=on_thinking)
    # A line shown live from an answer the check then rejected ends with the saved text, or
    # with null when its retried halves failed too.
    for number in sorted(result.lines):
        if sent.get(number) != result.lines[number]:
            chunk.emit(("line", {"line_number": number, "text": result.lines[number]}))
    for number in sorted(set(result.failed)):
        if number in sent:
            chunk.emit(("line", {"line_number": number, "text": None}))
    return result


async def _work(prep: _Prepared, key: _Key, chunk: _Chunk) -> None:
    """One by-hand chunk, counted as work in flight until it has saved."""
    try:
        with state.work():
            if not await _ask(prep, chunk):
                return  # needs_setup was the terminal event
        chunk.emit(("done", {}))
    except state.Maintenance:
        chunk.emit(("error", {"message": state.IN_PROGRESS}))
    except BackendError as exc:
        chunk.emit(("error", {"message": str(exc)}))
    except Exception:  # a failed save and the like; the traceback stays server-side
        log.exception("Ollama by-hand translation failed")
        chunk.emit(("error", {"message": "Ollama failed"}))
    finally:
        if _RUNNING.get(key) is chunk:
            del _RUNNING[key]
        chunk.finish()


async def _ask(prep: _Prepared, chunk: _Chunk) -> bool:
    """Wait for the lane, then reuse what is saved, or translate and save, in one hold: the
    commit lands before the next request on the lane rereads. False: it needs setup."""
    assert prep.ep is not None
    reason = LANES.wait_reason(prep.user_id)
    if reason:
        chunk.emit(("waiting", {"reason": reason}))
    async with LANES.hold(prep.user_id, priority=True):
        fresh = await run_in_threadpool(_reread, prep)
        if fresh.setup:
            chunk.emit(("needs_setup", {"message": fresh.setup}))
            return False
        if fresh.plan is None:
            for number, text in fresh.reused or []:
                chunk.emit(("line", {"line_number": number, "text": text}))
        else:
            async with http_client() as client:
                ep = await endpoint.ready(client, prep.ep)
                # the same steady window as a run with these prefs: no model reload
                ctx = steady_ctx(ep.system_prompt, prep.prefs.chunk_lines,
                                 prep.prefs.context_lines)
                result = await _translate(chunk, client, ep, fresh.plan, ctx)
            ids = await run_in_threadpool(_save, prep, fresh.plan, result)
            chunk.emit(("saved", {"chunk_ids": ids}))
    return True


def _ended(task: asyncio.Task) -> None:
    _TASKS.discard(task)
    if not task.cancelled() and task.exception() is not None:
        log.error("Ollama by-hand task failed", exc_info=task.exception())


def _start(prep: _Prepared) -> _Chunk:
    key = _key(prep, prep.reroll)
    chunk = _RUNNING[key] = _Chunk()
    task = asyncio.create_task(_work(prep, key, chunk))
    _TASKS.add(task)
    task.add_done_callback(_ended)
    return chunk


async def stop() -> None:
    """At shutdown: cancel the chunks in flight (what is saved stays)."""
    tasks = list(_TASKS)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


async def _events(prep: _Prepared) -> AsyncIterator[Event]:
    """Every stream ends with one terminal event: done, needs_setup or error. A request for a
    line of a chunk already in flight follows that chunk instead of asking again."""
    if prep.plan is None:
        yield ("done", {})
        return
    if prep.ep is None:
        yield ("needs_setup", {"message": prep.setup or "Ollama is not set up"})
        return
    chunk = _RUNNING.get(_key(prep, prep.reroll))
    if chunk is None and not prep.reroll:
        chunk = _RUNNING.get(_key(prep, True))  # a reroll in flight answers this line too
    if chunk is None:
        chunk = _start(prep)
    lines = prep.plan.chunk
    yield ("plan", {"first_line": lines[0].line_number, "last_line": lines[-1].line_number})
    async with aclosing(chunk.follow()) as events:
        async for event in events:
            yield event


@router.get("/documents/{document_id}/ollama/stream", response_class=StreamingResponse)
async def stream(
    document_id: int,
    line_number: int = Query(ge=0, le=2**31 - 1),
    reroll: bool = False,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> StreamingResponse:
    """Translate the chunk holding the line (reroll: every untranslated line in it)."""
    prep = await run_in_threadpool(_prepare, db, user.id, document_id, line_number, reroll)

    async def body() -> AsyncIterator[str]:
        async with aclosing(_events(prep)) as events:
            async for event in events:
                yield sse(event)

    return StreamingResponse(
        body(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
