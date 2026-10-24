"""Rules for a volume's Illustrations chapter: a text-free chapter, at most one per volume,
always inside a volume of a non-syosetu series. Each check raises ``IllustrationsRule``
whose message is the 409 detail. Also its WordPress upload (``upload``)."""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from api import publish
from api.core import wp, wp_http
from api.core.text import line_has_content
from api.core.wp import WPPublishError
from api.models import Document, DocumentImage, Line, Series, User, Volume

HAS_ONE = "this volume already has an Illustrations chapter"
TITLE = "Illustrations"
NO_IMAGES = "This volume has no illustrations to publish."


class IllustrationsRule(Exception):
    """A request would break an Illustrations-chapter rule."""


def rule_conflict(exc: IllustrationsRule) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


def volume_has_one(db: Session, volume_id: int, besides: int | None = None) -> bool:
    q = select(Document.id).where(
        Document.volume_id == volume_id, Document.is_illustrations.is_(True)
    )
    if besides is not None:
        q = q.where(Document.id != besides)
    return db.scalar(q.limit(1)) is not None


def check_mark(db: Session, doc: Document) -> None:
    """Marking ``doc`` is allowed: syosetu-free series, no text, in a volume with none yet."""
    if db.scalar(select(Series.syosetu_url).where(Series.id == doc.series_id)):
        raise IllustrationsRule("a syosetu series has no Illustrations chapter")
    texts = db.scalars(select(Line.raw_text).where(Line.document_id == doc.id))
    if any(line_has_content(t) for t in texts):
        raise IllustrationsRule("only a chapter with no text can be the Illustrations chapter")
    if doc.volume_id is None:
        raise IllustrationsRule("put the chapter in a volume first")
    if volume_has_one(db, doc.volume_id, besides=doc.id):
        raise IllustrationsRule(HAS_ONE)


def check_move(doc: Document, volume_id: int | None, db: Session) -> None:
    """A marked chapter may only move to another volume that has no Illustrations chapter."""
    if not doc.is_illustrations:
        return
    if volume_id is None:
        raise IllustrationsRule("the Illustrations chapter must stay in a volume")
    if volume_id != doc.volume_id and volume_has_one(db, volume_id, besides=doc.id):
        raise IllustrationsRule(HAS_ONE)


def check_no_text(doc: Document, raw: list[str]) -> None:
    """New source lines for a marked chapter must be text-free."""
    if doc.is_illustrations and any(line_has_content(r) for r in raw):
        raise IllustrationsRule("the Illustrations chapter can't hold text; unmark it first")


def add_images(
    db: Session, user: User, series: Series, volume: Volume, images: list[dict], order: int,
) -> Document | None:
    """Append ``images`` (extract_chapter_content dicts) to the volume's Illustrations chapter,
    creating it at series_order ``order``; a src_path it already holds is skipped. Returns the
    chapter, or None when no image was added (so none is created empty, and a re-import does
    not report it). The caller flushes and arranges."""
    doc = db.scalar(select(Document).where(
        Document.volume_id == volume.id, Document.is_illustrations.is_(True)))
    held = set() if doc is None else set(db.scalars(
        select(DocumentImage.src_path).where(DocumentImage.document_id == doc.id)))
    fresh = []
    for img in images:
        if img["src_path"] not in held:
            held.add(img["src_path"])
            fresh.append(img)
    if not fresh:
        return None
    if doc is None:
        doc = Document(
            user_id=user.id, series_id=series.id, volume_id=volume.id, title=TITLE,
            chapter_title=TITLE, series_order=order, is_illustrations=True,
        )
        db.add(doc)
        db.flush()
    db.add_all(
        DocumentImage(document_id=doc.id, anchor_position=0, is_cover=False,
                      src_path=img["src_path"], data=img["data"])
        for img in fresh
    )
    return doc


def has_images(db: Session, volume_id: int) -> bool:
    """Whether ``upload`` would find anything to send (the volume_images filter, no bytes)."""
    return db.scalar(
        select(DocumentImage.id).join(Document, Document.id == DocumentImage.document_id)
        .where(Document.volume_id == volume_id,
               or_(DocumentImage.is_cover, DocumentImage.exclude_export.is_(False)))
        .limit(1)
    ) is not None


def upload(
    db: Session, c: httpx.Client, doc: Document, endpoint: str, key: str,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Send the volume's illustrations page for the marked ``doc``: its own images first (it
    sorts first in the volume), then the rest of the volume's, in batches under the host's
    body limit. Records the result on ``doc`` like a published chapter, without a number."""
    series = doc.series
    if series is None or doc.volume_id is None:
        raise publish.NotReady(NO_IMAGES)
    publish.check_series(series)
    volume = db.get(Volume, doc.volume_id)
    inline, cover = publish.volume_images(db, volume.id)
    if not inline and cover is None:
        raise publish.NotReady(NO_IMAGES)
    payloads = wp.build_illustrations_payloads(
        {"series_title": series.title, "volume_title": volume.wp_name},
        publish.series_meta(series), inline, api_key=key, cover=cover)
    if progress:
        progress(0, len(payloads))
    first: dict | None = None
    for i, p in enumerate(payloads, start=1):
        try:
            result = wp_http.publish_illustrations(c, endpoint, p)
        except WPPublishError as exc:
            raise WPPublishError(f"batch {i}/{len(payloads)}: {exc.message}",
                                 exc.status_code) from exc
        if first is None:
            publish.freeze_volume_name(db, volume.id)
            first = result  # the desktop reports the first ("replace") answer
        if progress:
            progress(i, len(payloads))
    page_url = str(first.get("page_url") or "")
    doc.wp_status, doc.wp_post_url = "publish", page_url
    doc.wp_published_at, doc.wp_scheduled_for = datetime.now(UTC), None
    return {"page_url": page_url, "created": bool(first.get("created")),
            "batches": len(payloads), "images": len(inline) + (cover is not None)}
