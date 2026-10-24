"""Rules for a volume's Illustrations chapter: a text-free chapter, at most one per volume,
always inside a volume of a non-syosetu series. Each check raises ``IllustrationsRule``
whose message is the 409 detail."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.core.text import line_has_content
from api.models import Document, DocumentImage, Line, Series, User, Volume

HAS_ONE = "this volume already has an Illustrations chapter"
TITLE = "Illustrations"


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
