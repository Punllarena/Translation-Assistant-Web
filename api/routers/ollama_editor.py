"""Ollama in the editor (spec "The editor"): a chapter's held suggestions, one chunk's detail,
and by-hand translation of the chunk a line belongs to (SSE).

The stream goes through the user's lane ahead of a run's chunks (priority), but never cuts the
chunk in flight. Its save runs in its own session and commits, a sanctioned commit outside the
route boundary like the /mt/stream cache write (CLAUDE.md): the SSE body runs after the response
has started, when the request's session is no longer ours. The save happens while the lane is
still held, so a request waiting behind this one sees its results and reuses them.

A client that disconnects mid-chunk abandons it: the upstream request is closed and nothing is
saved (the answer is only checked once the whole chunk is back).
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

from api.db import SessionLocal
from api.deps import current_user, db_session, scoped
from api.models import Document, Line, User
from api.models.ollama import OllamaChunk, OllamaSuggestion
from api.mt.base import BackendError, Event, sse
from api.ollama import endpoint
from api.ollama.lane import LANES
from api.ollama.prefs import OllamaPrefs
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
    # Sanctioned commit in its own session: the request's session is no longer ours.
    with SessionLocal() as db:
        ids = save(db, prep.user_id, plan, result.requests, result.lines,
                   source="reroll" if prep.reroll else "manual", job_id=None, p=prep.prefs,
                   model=prep.ep.model)
        db.commit()
        return ids


async def _live(
    client: httpx.AsyncClient, ep: Endpoint, plan: Plan, out: list[ChunkResult]
) -> AsyncIterator[Event]:
    """translate()'s line and thinking callbacks as events; the result lands in `out`.
    Closing this generator cancels the translation, which closes the upstream request."""
    queue: asyncio.Queue[Event | None] = asyncio.Queue()

    async def on_line(number: int, text: str) -> None:
        queue.put_nowait(("line", {"line_number": number, "text": text}))

    async def on_thinking(text: str) -> None:
        queue.put_nowait(("thinking", {"text": text}))

    async def run() -> ChunkResult:
        try:
            return await translate(client, ep, plan.before, plan.chunk,
                                   on_line=on_line, on_thinking=on_thinking)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(run())
    try:
        while (event := await queue.get()) is not None:
            yield event
        out.append(task.result())  # raises what translate() raised
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def _ask(prep: _Prepared, plan: Plan) -> AsyncIterator[Event]:
    assert prep.ep is not None
    sent: dict[int, str] = {}
    out: list[ChunkResult] = []
    async with http_client() as client:
        ep = await endpoint.ready(client, prep.ep)
        async with aclosing(_live(client, ep, plan, out)) as events:
            async for kind, data in events:
                if kind == "line":
                    sent[data["line_number"]] = data["text"]
                yield (kind, data)
    result = out[0]
    # A line shown live from an answer the check then rejected ends with the saved text.
    for number in sorted(result.lines):
        if sent.get(number) != result.lines[number]:
            yield ("line", {"line_number": number, "text": result.lines[number]})
    ids = await run_in_threadpool(_save, prep, plan, result)
    yield ("saved", {"chunk_ids": ids})


async def _events(prep: _Prepared) -> AsyncIterator[Event]:
    """Every stream ends with exactly one terminal event: done, needs_setup or error."""
    if prep.plan is None:
        yield ("done", {})
        return
    if prep.ep is None:
        yield ("needs_setup", {"message": prep.setup or "Ollama is not set up"})
        return
    chunk = prep.plan.chunk
    yield ("plan", {"first_line": chunk[0].line_number, "last_line": chunk[-1].line_number})
    if LANES.busy(prep.user_id):
        yield ("waiting", {})
    try:
        async with LANES.hold(prep.user_id, priority=True):
            fresh = await run_in_threadpool(_reread, prep)
            if fresh.setup:
                yield ("needs_setup", {"message": fresh.setup})
                return
            if fresh.plan is None:
                for number, text in fresh.reused or []:
                    yield ("line", {"line_number": number, "text": text})
            else:
                async with aclosing(_ask(prep, fresh.plan)) as events:
                    async for event in events:
                        yield event
    except BackendError as exc:
        yield ("error", {"message": str(exc)})
        return
    except Exception:  # a failed save and the like; the traceback stays server-side
        log.exception("Ollama by-hand translation failed")
        yield ("error", {"message": "Ollama failed"})
        return
    yield ("done", {})


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
