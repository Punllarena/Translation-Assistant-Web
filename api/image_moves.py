"""Moving images rather than losing them: a chapter's ``document_images`` go to the end of
its volume's Illustrations chapter (creating it), and a name the chapter already holds is
renamed, never dropped. Used by ``DELETE /documents/{id}?images=move`` and the Gallery."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api import illustrations
from api.illustrations import IllustrationsRule
from api.library import arrange
from api.models import Document, DocumentImage, Series, User, Volume

NO_VOLUME = "a chapter outside a volume has no Illustrations chapter"
IS_ILLUSTRATIONS = "these images are already in the Illustrations chapter"


def free_name(held: set[str], name: str) -> str:
    """``name`` if nothing holds it, else ``stem-2.ext``, ``stem-3.ext``, ..."""
    if name not in held:
        return name
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    n = 2
    while f"{stem}-{n}{dot}{ext}" in held:
        n += 1
    return f"{stem}-{n}{dot}{ext}"


def check_can_move(db: Session, doc: Document) -> Volume:
    """The volume whose Illustrations chapter may take ``doc``'s images; raises
    ``IllustrationsRule`` when none may (the 409 detail)."""
    if doc.volume_id is None:
        raise IllustrationsRule(NO_VOLUME)
    if illustrations.is_syosetu(db, doc.series_id):
        raise IllustrationsRule(illustrations.SYOSETU)
    if doc.is_illustrations:
        raise IllustrationsRule(IS_ILLUSTRATIONS)
    return db.get(Volume, doc.volume_id)


def move_images(
    db: Session, user: User, volume: Volume, images: list[DocumentImage], order: int
) -> Document:
    """Append ``images`` to the end of ``volume``'s Illustrations chapter, creating it at
    ``series_order`` ``order`` when the volume has none; a src_path it already holds is
    renamed. Returns the chapter. The caller flushes and arranges."""
    doc = db.scalar(
        select(Document).where(
            Document.volume_id == volume.id, Document.is_illustrations.is_(True)
        )
    )
    if doc is None:
        doc = Document(
            user_id=user.id,
            series_id=volume.series_id,
            volume_id=volume.id,
            title=illustrations.TITLE,
            chapter_title=illustrations.TITLE,
            series_order=order,
            is_illustrations=True,
        )
        db.add(doc)
        db.flush()
    held = set(
        db.scalars(
            select(DocumentImage.src_path).where(DocumentImage.document_id == doc.id)
        )
    )
    top = (
        db.scalar(
            select(func.max(DocumentImage.anchor_position)).where(
                DocumentImage.document_id == doc.id
            )
        )
        or 0
    )
    for img in images:
        name = free_name(held, img.src_path)
        held.add(name)
        img.document_id = doc.id
        img.src_path = name
        top += 1
        img.anchor_position = top
        db.flush()  # one at a time: ids follow the order
    return doc


def drop_if_empty(db: Session, doc: Document) -> bool:
    """Delete ``doc`` when it is an Illustrations chapter left with no images and arrange its
    series; report whether it did. Its WordPress illustrations page is left untouched."""
    if not doc.is_illustrations:
        return False
    if db.scalar(
        select(DocumentImage.id).where(DocumentImage.document_id == doc.id).limit(1)
    ) is not None:
        return False
    series = db.get(Series, doc.series_id)
    db.delete(doc)
    db.flush()
    arrange(db, series)
    db.flush()
    return True
