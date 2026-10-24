"""Rules for a volume's Illustrations chapter: a text-free chapter, at most one per volume,
always inside a volume of a non-syosetu series. Each check raises ``IllustrationsRule``
whose message is the 409 detail."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.core.text import line_has_content
from api.models import Document, Line, Series

HAS_ONE = "this volume already has an Illustrations chapter"


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
