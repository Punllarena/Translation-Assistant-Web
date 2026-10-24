"""WordPress (spec §10): preferences, connection test, status refresh, one-chapter
publish, and the batch publish and Illustrations chapter upload jobs (api/publish_job.py)."""

from dataclasses import asdict
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import api.publish_job  # noqa: F401  registers the wp_* handlers
from api import illustrations, jobs, publish, wp_prefs
from api.core import wp_http
from api.core.wp import WPPublishError
from api.deps import current_user, db_session, owned_ref, parse_zone, scoped, zone
from api.library import chapter_number
from api.models import Document, Job, Series, User
from api.routing import api_router
from api.schemas.jobs import JobOut
from api.schemas.wp import (
    BatchPublishIn,
    IllustrationsIn,
    PublishIn,
    PublishOut,
    WpPrefsOut,
    WpStatusOut,
    WpTestOut,
)

router = api_router(tags=["wp"])

http_client = wp_http.client  # the seam tests replace
PROBE_SLUG = "ta-web-connection-test"
UPLOAD_BUSY = "an illustrations upload is already queued or running"
ACTIVE = ("queued", "running")


def _ready(fn, *args):
    """Run a publish step; NotReady is the user's to fix, so a 422 with its message."""
    try:
        return fn(*args)
    except publish.NotReady as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("/wp/prefs", response_model=WpPrefsOut)
def get_prefs(user: User = Depends(current_user), db: Session = Depends(db_session)) -> WpPrefsOut:
    return WpPrefsOut(**asdict(wp_prefs.load(db, user.id)))


@router.post("/wp/test", response_model=WpTestOut)
def test_connection(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> WpTestOut:
    """Ruling 13: ask /status with the saved key; not_found for the probe slug is success."""
    endpoint, key = _ready(publish.wp_config, db, user.id)
    try:
        with http_client() as c:
            wp_http.check_status(c, endpoint, key, PROBE_SLUG, 1)
    except WPPublishError as exc:
        if exc.status_code == 401:
            return WpTestOut(ok=False, message="WordPress answered, but rejected the API key.")
        return WpTestOut(ok=False, message=exc.message)
    return WpTestOut(ok=True, message="Connected; WordPress accepted the API key.")


def _chapter_context(
    db: Session, document_id: int, user_id: int
) -> tuple[Document, Series, str, str]:
    doc = scoped(db, Document, document_id, user_id)
    endpoint, key = _ready(publish.wp_config, db, user_id)
    if doc.series is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Only a chapter in a series can be published.")
    _ready(publish.check_series, doc.series)
    return doc, doc.series, endpoint, key


@router.post("/documents/{document_id}/wp/status", response_model=WpStatusOut)
def refresh_status(
    document_id: int, tz: ZoneInfo = Depends(zone),
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> WpStatusOut:
    """What the desktop confirm dialog showed: the cached and live status, and whether the
    previous chapter is still scheduled (with the auto slot after it)."""
    doc, series, endpoint, key = _chapter_context(db, document_id, user.id)
    cached, remote_error = doc.wp_status, ""
    if doc.is_illustrations:  # not a numbered chapter: nothing to ask WordPress about
        return WpStatusOut(cached_status=cached, status=cached, post_url=doc.wp_post_url,
                           remote_error="", previous_scheduled=False, suggested_slot=None)
    try:
        with http_client() as c:
            remote = wp_http.check_status(c, endpoint, key, series.wp_series_slug,
                                         chapter_number(db, doc))
            publish.apply_remote_status(doc, remote)
    except WPPublishError as exc:
        remote_error = exc.message
    previous, slot = publish.suggested_slot(db, doc, wp_prefs.load(db, user.id), tz)
    db.flush()
    return WpStatusOut(cached_status=cached, status=doc.wp_status, post_url=doc.wp_post_url,
                       remote_error=remote_error, previous_scheduled=previous, suggested_slot=slot)


# ponytail: a publish request holds a pool connection for up to ~25 s (status + publish
# timeouts); make it a job if that starves the pool
@router.post("/documents/{document_id}/wp/publish", response_model=PublishOut)
def publish_chapter(
    document_id: int, body: PublishIn,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> PublishOut:
    """The desktop run_single_publish, with the re-publish safeguard enforced (ruling 6)."""
    doc, series, endpoint, key = _chapter_context(db, document_id, user.id)
    prefs = wp_prefs.load(db, user.id)
    ch = _ready(publish.build_chapter, db, doc, prefs)
    with http_client() as c:
        live = doc.wp_status in publish.LIVE
        try:
            remote = wp_http.check_status(c, endpoint, key, series.wp_series_slug,
                                         chapter_number(db, doc))
            live = live or remote.get("status") in publish.LIVE
        except WPPublishError:
            pass  # WordPress could not be asked: the cached status decides, as on the desktop
        if live and not body.confirm_republish:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f'"{doc.title}" is already published or scheduled on WordPress; '
                "publishing again overwrites it.")
        try:
            result = wp_http.publish(c, endpoint, publish.payload(
                ch, key, scheduled=body.scheduled_for, attribution=prefs.wp_attribution_enabled))
        except WPPublishError as exc:
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, exc.message) from exc
    written = publish.record(doc, result, body.scheduled_for, ch.doc_meta["series_order"])
    if written:
        publish.freeze_volume_name(db, doc.volume_id)
    db.flush()
    return PublishOut(
        created=bool(result.get("created")), updated=bool(result.get("updated")),
        page_url=str(result.get("page_url") or ""), post_url=str(result.get("post_url") or ""),
        password=ch.password if written else None,
        unlock_chapter_index=ch.unlock_chapter_index if written else None,
        scheduled_for=body.scheduled_for,
    )


@router.post("/wp/batch", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def batch_publish(
    body: BatchPublishIn, user: User = Depends(current_user), db: Session = Depends(db_session),
) -> Job:
    """The desktop Publish / Schedule Chapters: checks up front, slots computed now
    (desktop loop), the publishing itself in a job."""
    tz = parse_zone(body.tz)
    _ready(publish.wp_config, db, user.id)
    docs = [owned_ref(db, Document, i, user.id, "document_ids")
            for i in dict.fromkeys(body.document_ids)]
    for series in {d.series_id: d.series for d in docs}.values():
        if series is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                "Only chapters in a series can be published.")
        _ready(publish.check_series, series)
    if db.scalar(select(Job.id).where(
        Job.user_id == user.id, Job.kind == "wp_publish", Job.state.in_(ACTIVE),
    ).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "a batch publish is already queued or running")
    if any(d.is_illustrations for d in docs) and _active(db, user.id, "wp_illustrations"):
        raise HTTPException(status.HTTP_409_CONFLICT, UPLOAD_BUSY)
    docs.sort(key=lambda d: (d.series.title, d.series_order, d.id))
    prefs = wp_prefs.load(db, user.id)
    # the Illustrations chapter takes no slot: its endpoint takes no date
    numbered = sum(not d.is_illustrations for d in docs)
    slots = iter(publish.batch_slots(body.start, numbered, body.chapters_per_day,
                                     prefs.wp_default_schedule_time, tz)
                 if body.schedule else [None] * numbered)
    chapters = []
    for d in docs:
        s = None if d.is_illustrations else next(slots)
        chapters.append({"document_id": d.id, "scheduled_for": s.isoformat() if s else None})
    return jobs.enqueue(db, user.id, "wp_publish",
                        {"chapters": chapters, "confirm_republish": body.confirm_republish},
                        total=len(chapters))


def _active(db: Session, user_id: int, kind: str) -> list[Job]:
    return list(db.scalars(select(Job).where(
        Job.user_id == user_id, Job.kind == kind, Job.state.in_(ACTIVE))))


@router.post("/documents/{document_id}/wp/illustrations", response_model=JobOut,
             status_code=status.HTTP_202_ACCEPTED)
def publish_illustrations(
    document_id: int, body: IllustrationsIn,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> Job:
    """The Illustrations chapter's Publish: the volume's illustrations page, as a job. The
    plugin has no status lookup for that page, so the stored status guards re-publishing."""
    doc, series, _, _ = _chapter_context(db, document_id, user.id)
    if not doc.is_illustrations:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "Only the Illustrations chapter is published this way.")
    if doc.volume_id is None or not illustrations.has_images(db, doc.volume_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, illustrations.NO_IMAGES)
    if doc.wp_status in publish.LIVE and not body.confirm_republish:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "already published; publishing again overwrites the illustrations page")
    if _active(db, user.id, "wp_illustrations") or any(
        c["document_id"] == doc.id
        for j in _active(db, user.id, "wp_publish") for c in j.params_json["chapters"]
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, UPLOAD_BUSY)
    return jobs.enqueue(db, user.id, "wp_illustrations",
                        {"document_id": doc.id, "series_id": series.id})
