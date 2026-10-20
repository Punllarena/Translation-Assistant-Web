"""Syosetu acquisition (spec §6, §9): fetch one chapter's text, list a series'
chapters, fetch a series as a job, and re-fetch a chapter's source."""

import threading
from contextlib import contextmanager

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import api.fetch_job  # noqa: F401  registers the syosetu_fetch handler
from api import jobs, server_settings
from api.core import scrape
from api.core.text import build_new_file, parse_file_content
from api.deps import current_user, db_session, scoped
from api.fetch_job import existing_orders
from api.library import replace_raw_lines
from api.models import Document, Job, Series, User
from api.routing import api_router
from api.schemas.documents import DocumentOut
from api.schemas.jobs import JobOut
from api.schemas.scrape import FetchChapters, Fetched, FetchUrl, IndexChapter, Refetch

router = api_router(tags=["scrape"])

http_client = scrape.client  # the seam tests replace

# Request paths hold a pool connection and a worker thread while they wait on the
# process-wide throttle, so at most two wait at once; the job worker does not use this.
syosetu_slots = threading.BoundedSemaphore(2)


@contextmanager
def _slot():
    if not syosetu_slots.acquire(blocking=False):
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "syosetu is busy, try again shortly")
    try:
        yield
    finally:
        syosetu_slots.release()


def _fetch(url: str, delay: float) -> tuple[str, str]:
    try:
        with _slot(), http_client() as c:
            return scrape.fetch_syosetu(c, url, delay=delay)
    except scrape.ScrapeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("/scrape/syosetu", response_model=Fetched)
def fetch_one(
    body: FetchUrl, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Fetched:
    """The desktop New document → Fetch from URL tab: returns the text for the form."""
    title, content = _fetch(body.url, server_settings.effective(db).syosetu_delay_seconds)
    return Fetched(title=title, content=content)


def _series_with_url(db: Session, series_id: int, user_id: int) -> Series:
    series = scoped(db, Series, series_id, user_id)
    if not series.syosetu_url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "the series has no syosetu URL")
    return series


@router.get("/series/{series_id}/syosetu/chapters", response_model=list[IndexChapter])
def list_chapters(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[IndexChapter]:
    series = _series_with_url(db, series_id, user.id)
    try:
        with _slot(), http_client() as c:
            index = scrape.fetch_series_index(c, series.syosetu_url)
    except scrape.ScrapeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    have = existing_orders(db, series.id)
    return [IndexChapter(**ch, fetched=ch["num"] in have) for ch in index]


@router.post(
    "/series/{series_id}/syosetu/fetch", response_model=JobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def fetch_series(
    series_id: int, body: FetchChapters,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> Job:
    series = _series_with_url(db, series_id, user.id)
    if db.scalar(select(Job.id).where(
        Job.user_id == user.id, Job.kind == "syosetu_fetch",
        Job.state.in_(("queued", "running")),
        Job.params_json["series_id"].as_integer() == series.id,
    ).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "a fetch for this series is already queued or running")
    nums = sorted(set(body.nums))
    return jobs.enqueue(db, user.id, "syosetu_fetch",
                        {"series_id": series.id, "nums": nums}, total=len(nums))


@router.post("/documents/{document_id}/refetch", response_model=DocumentOut)
def refetch(
    document_id: int, body: Refetch,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> Document:
    """The desktop Re-fetch: the title, a blank line, then the text, re-split into
    lines; translations stay attached by position (409 on a line-count change)."""
    doc = scoped(db, Document, document_id, user.id)
    if not doc.source_url:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "this chapter has no source URL")
    title, content = _fetch(doc.source_url, server_settings.effective(db).syosetu_delay_seconds)
    raw, _, _ = parse_file_content(build_new_file(f"{title}\n\n{content}" if title else content))
    replace_raw_lines(db, doc, raw, body.force)
    return doc
