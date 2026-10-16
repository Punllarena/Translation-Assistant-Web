"""Machine-translation aggregator (spec §8): per-user availability, and one SSE stream
per backend and line. HTTP backends are cached in mt_cache (ruling 8); the stream writes
the cache in its own session because it finishes after the response has started
(ruling 10)."""

import logging
from collections.abc import AsyncIterator
from contextlib import aclosing
from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, Query, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import server_settings
from api.db import SessionLocal
from api.deps import current_user, db_session, scoped
from api.models import ApiCredential, Document, Line, User, UserSetting
from api.mt import cache, deepl, jparser, libretranslate, mecab, ollama, prefs
from api.mt.base import ANALYZERS, HTTP_BACKENDS, BackendError, Event, NeedsSetup, sse
from api.mt.languages import LANGUAGES
from api.mt.prefs import LABELS, NOT_SET, Prefs
from api.mt.urls import check_user_url
from api.routers.credentials import load_secret
from api.routers.lines import display_line
from api.routing import api_router
from api.schemas.mt import Backend, Backends, BackendStatus

router = api_router(prefix="/mt", tags=["mt"])
log = logging.getLogger(__name__)


def http_client() -> httpx.AsyncClient:
    """The seam tests replace with an httpx.MockTransport client (spec §12)."""
    return httpx.AsyncClient()  # follow_redirects stays False: a redirect is no SSRF bypass


@dataclass
class Job:
    backend: str
    text: str = ""
    src: str = ""
    dst: str = ""
    key: str = ""        # DeepL key / LibreTranslate key / Ollama bearer token
    url: str = ""        # LibreTranslate / Ollama endpoint
    model: str = ""
    prompt: str = ""
    cache_key: str = ""  # mt_cache.backend (per endpoint) for a configured HTTP backend
    cached: str | None = None
    setup: str | None = None  # a needs_setup message found while preparing


def _prefs(db: Session, user_id: int) -> Prefs:
    rows = db.execute(
        select(UserSetting.key, UserSetting.value_json).where(
            UserSetting.user_id == user_id, UserSetting.key.in_(prefs.KEYS)
        )
    )
    return prefs.parse({key: value for key, value in rows})


def _configure(db: Session, user_id: int, backend: str, p: Prefs) -> Job:
    """Credentials, endpoint and model for an HTTP backend. Blocking (DNS, decryption)."""
    job = Job(backend=backend)
    if backend in ANALYZERS:
        return job
    settings = server_settings.effective(db)
    cred_url = db.scalar(
        select(ApiCredential.endpoint_url).where(
            ApiCredential.user_id == user_id,
            ApiCredential.kind == backend,
            ApiCredential.name == "",
        )
    )
    try:
        job.key = load_secret(db, user_id, backend) or ""  # "" for a key-less credential
    except ValueError:  # undecryptable, e.g. after a TA_SECRET_KEY change
        job.setup = prefs.unreadable_key(backend)
        return job
    if backend == "deepl":
        job.cache_key = "deepl" if job.key else ""
        return job
    if cred_url:  # the user's own endpoint: user input, so guarded against SSRF
        job.url = cred_url
        job.setup = check_user_url(cred_url, settings.mt_allow_private_urls, LABELS[backend])
    else:  # the operator's default, trusted
        job.url = (
            settings.libretranslate_url if backend == "libretranslate" else settings.ollama_url
        )
    if backend == "libretranslate":
        job.cache_key = prefs.libretranslate_cache_key(job.url) if job.url else ""
    else:
        job.model, job.prompt = p.ollama_model, p.ollama_prompt
        if not job.url:
            job.setup = job.setup or prefs.NO_OLLAMA_URL
        if job.model:
            job.cache_key = prefs.ollama_cache_key(job.url, job.model, job.prompt)
    return job


def _prepare(
    db: Session, user_id: int, backend: str, document_id: int, line_number: int,
    profile_id: int | None,
) -> Job:
    doc = scoped(db, Document, document_id, user_id)
    line = db.scalar(
        select(Line).where(Line.document_id == doc.id, Line.line_number == line_number)
    )
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    text = display_line(db, user_id, doc, line, profile_id)  # 422 for a foreign profile_id
    p = _prefs(db, user_id)
    job = _configure(db, user_id, backend, p) if text else Job(backend=backend)
    job.text, job.src, job.dst = text, doc.source_language or "ja", p.target
    if text and job.cache_key and not job.setup:
        job.cached = cache.get(db, job.cache_key, job.src, job.dst, text)
    return job


def _put_sync(job: Job, result: str) -> None:
    with SessionLocal() as s:  # ruling 10: the request's session is gone by now
        cache.put(s, job.cache_key, job.src, job.dst, job.text, result)
        s.commit()


async def _put(job: Job, result: str) -> None:
    # The user already has the result; a failed cache write must not turn it into an error.
    try:
        await run_in_threadpool(_put_sync, job, result)
    except Exception:
        log.exception("mt_cache write failed for %s", job.backend)


async def _translate(job: Job) -> AsyncIterator[Event]:
    if job.backend in ANALYZERS:
        run = jparser.run if job.backend == "jparser" else mecab.run
        yield ("analysis", {"entries": await run_in_threadpool(run, job.text)})
        return
    async with http_client() as client:
        if job.backend == "ollama":
            parts: list[str] = []
            gen = ollama.stream(client, job.url, job.key, job.model, job.prompt,
                                job.text, job.src, job.dst)
            async with aclosing(gen) as upstream:  # a disconnect closes the upstream request
                async for kind, data in upstream:
                    if kind == "chunk":
                        parts.append(data["text"])
                    yield (kind, data)
            result = "".join(parts)  # reached only when the stream completed (ruling 8)
        elif job.backend == "deepl":
            result = await deepl.translate(client, job.key, job.text, job.src, job.dst)
            yield ("result", {"text": result})
        else:
            result = await libretranslate.translate(
                client, job.url, job.key, job.text, job.src, job.dst
            )
            yield ("result", {"text": result})
    if result:
        await _put(job, result)


async def _events(job: Job) -> AsyncIterator[Event]:
    """Every stream ends with exactly one terminal event: done, needs_setup or error."""
    if not job.text:
        yield ("done", {"cached": False})
        return
    if job.setup:
        yield ("needs_setup", {"message": job.setup})
        return
    if job.cached is not None:
        yield ("result", {"text": job.cached})
        yield ("done", {"cached": True})
        return
    try:
        async with aclosing(_translate(job)) as events:
            async for event in events:
                yield event
    except NeedsSetup as exc:
        yield ("needs_setup", {"message": str(exc)})
        return
    except BackendError as exc:
        yield ("error", {"message": str(exc)})
        return
    except Exception:  # a malformed 200 body and the like; the traceback stays server-side
        log.exception("%s failed", LABELS[job.backend])
        yield ("error", {"message": f"{LABELS[job.backend]} failed"})
        return
    yield ("done", {"cached": False})


@router.get("/stream", response_class=StreamingResponse)
async def stream(
    backend: Backend,
    document_id: int,
    line_number: int = Query(ge=0, le=2**31 - 1),
    profile_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> StreamingResponse:
    job = await run_in_threadpool(
        _prepare, db, user.id, backend, document_id, line_number, profile_id
    )

    async def body() -> AsyncIterator[str]:
        async with aclosing(_events(job)) as events:
            async for event in events:
                yield sse(event)

    return StreamingResponse(
        body(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _analyzer_status(name: str) -> str | None:
    try:
        (jparser.run if name == "jparser" else mecab.run)("")  # loads, analyses nothing
    except NeedsSetup as exc:
        return str(exc)
    return None


def _status_prepare(db: Session, user_id: int) -> tuple[Prefs, dict[str, Job], dict]:
    p = _prefs(db, user_id)
    jobs = {name: _configure(db, user_id, name, p) for name in HTTP_BACKENDS}
    return p, jobs, {name: _analyzer_status(name) for name in sorted(ANALYZERS)}


@router.get("/backends", response_model=Backends)
async def backends(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Backends:
    p, jobs, local = await run_in_threadpool(_status_prepare, db, user.id)
    problems: dict[str, str | None] = {}
    for name, job in jobs.items():
        ready = {"deepl": job.key, "libretranslate": job.url, "ollama": job.model}[name]
        problems[name] = job.setup or (None if ready else NOT_SET[name])
    if problems["ollama"] is None:
        job = jobs["ollama"]
        async with http_client() as client:
            problems["ollama"] = await ollama.available(client, job.url, job.key)
    problems |= local
    return Backends(
        languages=LANGUAGES, target=p.target, enabled=p.enabled,
        ollama_default_prompt=ollama.DEFAULT_SYSTEM_PROMPT,
        backends=[
            BackendStatus(name=name, available=problems[name] is None, message=problems[name])
            for name in ("deepl", "libretranslate", "ollama", "mecab", "jparser")
        ],
    )
