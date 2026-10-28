"""Rules for a volume's Illustrations chapter: a text-free chapter, at most one per volume,
always inside a volume of a non-syosetu series. Each check raises ``IllustrationsRule``
whose message is the 409 detail. Also its WordPress upload (``upload``)."""

from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from api import publish
from api.core import wp, wp_http
from api.core.text import line_has_content
from api.core.wp import WPPublishError
from api.library import first_chapter_number
from api.models import Document, DocumentImage, Line, Series, User, Volume, VolumeCover

HAS_ONE = "this volume already has an Illustrations chapter"
TITLE = "Illustrations"
NO_IMAGES = "This volume has no illustrations to publish."
SYOSETU = "a syosetu series has no Illustrations chapter"


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
    if _syosetu(db, doc.series_id):
        raise IllustrationsRule(SYOSETU)
    texts = db.scalars(select(Line.raw_text).where(Line.document_id == doc.id))
    if any(line_has_content(t) for t in texts):
        raise IllustrationsRule("only a chapter with no text can be the Illustrations chapter")
    if doc.volume_id is None:
        raise IllustrationsRule("put the chapter in a volume first")
    if volume_has_one(db, doc.volume_id, besides=doc.id):
        raise IllustrationsRule(HAS_ONE)


def _syosetu(db: Session, series_id: int) -> bool:
    return bool(db.scalar(select(Series.syosetu_url).where(Series.id == series_id)))


def check_move(
    doc: Document, volume_id: int | None, db: Session, series_id: int | None = None,
) -> None:
    """A marked chapter may only move to another volume, of a non-syosetu series
    (``series_id``, default its own), that has no Illustrations chapter."""
    if not doc.is_illustrations:
        return
    if _syosetu(db, doc.series_id if series_id is None else series_id):
        raise IllustrationsRule(SYOSETU)
    if volume_id is None:
        raise IllustrationsRule("the Illustrations chapter must stay in a volume")
    if volume_id != doc.volume_id and volume_has_one(db, volume_id, besides=doc.id):
        raise IllustrationsRule(HAS_ONE)


def unmark_syosetu(db: Session, series: Series) -> None:
    """A series that just became a syosetu series keeps its Illustrations chapters as
    ordinary chapters (the caller arranges)."""
    if series.syosetu_url:
        db.execute(update(Document).where(
            Document.series_id == series.id, Document.is_illustrations.is_(True),
        ).values(is_illustrations=False))


def merge_into(db: Session, keep_id: int, losers: list[int]) -> None:
    """Fold the losing Illustrations chapters' images into ``keep_id`` after its own, in
    order (fresh rows, so they also sort after it by id), skipping a src_path it already
    holds, then delete the losers with their remaining rows."""
    held = set(db.scalars(select(DocumentImage.src_path)
                          .where(DocumentImage.document_id == keep_id)))
    top = db.scalar(select(func.max(DocumentImage.anchor_position))
                    .where(DocumentImage.document_id == keep_id)) or 0
    for doc_id in losers:
        rows = db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc_id)
                          .order_by(DocumentImage.anchor_position, DocumentImage.id))
        for img in rows:
            if img.src_path in held:
                continue
            held.add(img.src_path)
            db.add(DocumentImage(
                document_id=keep_id, anchor_position=max(img.anchor_position, top),
                src_path=img.src_path, data=img.data,
                exclude_export=img.exclude_export,
            ))
            db.flush()  # one at a time: ids follow the order
    db.execute(delete(Document).where(Document.id.in_(losers)))


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
        DocumentImage(document_id=doc.id, anchor_position=0,
                      src_path=img["src_path"], data=img["data"])
        for img in fresh
    )
    return doc


def has_images(db: Session, volume_id: int) -> bool:
    """Whether ``upload`` would find anything to send (the volume_images filter, no bytes)."""
    return db.scalar(
        select(DocumentImage.id).join(Document, Document.id == DocumentImage.document_id)
        .where(Document.volume_id == volume_id, DocumentImage.exclude_export.is_(False))
        .limit(1)
    ) is not None or db.scalar(
        select(VolumeCover.id).where(VolumeCover.volume_id == volume_id)) is not None


def upload(
    db: Session, c: httpx.Client, doc: Document, endpoint: str, key: str,
    progress: Callable[[int, int], None] | None = None, *,
    scheduled: datetime | None = None,
) -> dict:
    """Send the volume's illustrations page for the marked ``doc``: its own images first (it
    sorts first in the volume), then the rest of the volume's, in batches under the host's
    body limit. Records the result on ``doc`` like a published chapter, without a number.
    A ``scheduled`` time goes on the first (replace) batch only."""
    series = doc.series
    if series is None or doc.volume_id is None:
        raise publish.NotReady(NO_IMAGES)
    publish.check_series(series)
    volume = db.get(Volume, doc.volume_id)
    inline, cover = publish.volume_images(db, volume.id)
    if not inline and cover is None:
        raise publish.NotReady(NO_IMAGES)
    payloads = wp.build_illustrations_payloads(
        {"series_title": series.title, "volume_title": volume.wp_name,
         "first_chapter_index": first_chapter_number(db, volume.id)},
        publish.series_meta(series), inline, api_key=key, cover=cover,
        scheduled_date=publish.wp_date(scheduled) if scheduled else None)
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
    doc.wp_status = "future" if scheduled else "publish"
    doc.wp_post_url = page_url
    doc.wp_published_at = scheduled or datetime.now(UTC)
    doc.wp_scheduled_for = scheduled
    return {"page_url": page_url, "created": bool(first.get("created")),
            "batches": len(payloads), "images": len(inline) + (cover is not None)}
