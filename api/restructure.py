"""Merge and split, ported from the desktop ``Database.merge_documents`` /
``split_document`` (f1a96ce) as the reference behaviour.

One change of method: lines and images are *moved* (UPDATE of document_id and
line_number) rather than deleted and re-inserted, so every line keeps its
``translated_at`` and the stats history survives a restructure. The desktop's
``save_lines`` re-keyed timestamps by line number and lost them.
"""

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from api.library import chapters, renumber
from api.models import Document, DocumentImage, Line


class RestructureError(ValueError):
    """The merge or split cannot be done as asked (the API answers 422)."""


class NotOwned(Exception):
    """A named document is missing or someone else's (the route decides the status: 422
    for body ids, 404 for the URL id)."""


def _line_end(db: Session, document_id: int) -> int:
    """One past the last line number: where appended lines start."""
    return db.scalar(
        select(func.coalesce(func.max(Line.line_number) + 1, 0)).where(
            Line.document_id == document_id
        )
    )


def merge_documents(
    db: Session, user_id: int, doc_ids: list[int], merged_title: str
) -> Document:
    """Merge 2+ chapters of one series into the lowest-series_order one.

    The others' lines are appended in series order (each one's first line forced to a
    '%' paragraph start), their images re-anchored by the same offset, and their rows
    deleted. The survivor keeps its id, volume, and wp_* fields and takes
    ``merged_title`` as its chapter_title; the series is renumbered 1..N.
    Everything is validated before the first write.
    """
    if len(doc_ids) < 2:
        raise RestructureError("merge needs at least two documents")
    if len(set(doc_ids)) != len(doc_ids):
        raise RestructureError("a document is listed twice")
    docs = list(
        db.scalars(
            select(Document).where(Document.id.in_(doc_ids), Document.user_id == user_id)
        )
    )
    if len(docs) != len(doc_ids):
        raise NotOwned
    if len({doc.series_id for doc in docs}) != 1:
        raise RestructureError("cannot merge documents from different series")
    docs.sort(key=lambda doc: (doc.series_order, doc.id))
    target, others = docs[0], docs[1:]

    offset = _line_end(db, target.id)
    for doc in others:
        length = _line_end(db, doc.id)
        db.execute(
            update(Line)
            .where(Line.document_id == doc.id, Line.line_number == 0)
            .values(prefix="%")
        )
        db.execute(
            update(Line)
            .where(Line.document_id == doc.id)
            .values(document_id=target.id, line_number=Line.line_number + offset)
        )
        db.execute(
            update(DocumentImage)
            .where(DocumentImage.document_id == doc.id)
            .values(document_id=target.id, anchor_position=DocumentImage.anchor_position + offset)
        )
        offset += length
    # A bulk delete, not session.delete(): the ORM cascade would also delete any Line
    # objects still sitting in a loaded `doc.lines` collection, which have just moved.
    db.execute(delete(Document).where(Document.id.in_([doc.id for doc in others])))

    target.chapter_title = merged_title
    renumber(chapters(db, target.series_id))
    db.flush()
    db.expire_all()  # loaded line/image collections are stale after the moves
    return target


def split_document(
    db: Session, user_id: int, doc_id: int, cuts: list[tuple[int, str]]
) -> list[Document]:
    """Split one chapter into consecutive segments at ``cuts``.

    ``cuts`` is ``[(start_line_number, title), ...]``, strictly increasing, each
    ``1 <= start <= last line``. Segment 0 stays in ``doc_id`` with its id, title, and
    wp_* fields. Each later segment becomes a new document in the same series and
    volume, titled as given (blank: ``"<chapter title> (n)"``), with its first line
    forced to a '%' paragraph start. Images move with the segment their anchor falls
    in; the last segment also takes any image anchored after the final line (a
    closing illustration), which the desktop left stranded on segment 0. The new
    chapters take the series slots right after the original, and the series is
    renumbered 1..N. Returns ``[original, new, ...]`` in segment order.
    """
    doc = db.scalar(select(Document).where(Document.id == doc_id, Document.user_id == user_id))
    if doc is None:
        raise NotOwned
    if not cuts:
        raise RestructureError("split needs at least one cut")
    starts = [start for start, _ in cuts]
    if starts != sorted(set(starts)):
        raise RestructureError("cut points must be strictly increasing")
    if starts[0] < 1 or starts[-1] > _line_end(db, doc.id) - 1:
        raise RestructureError("cut points out of range")

    siblings = chapters(db, doc.series_id)
    base_name = doc.chapter_title or doc.title
    ends: list[int | None] = [*starts[1:], None]  # None: through the end of the chapter
    new_docs: list[Document] = []
    for n, ((lo, title), hi) in enumerate(zip(cuts, ends, strict=True), start=2):
        name = title.strip() or f"{base_name} ({n})"
        new = Document(
            user_id=user_id,
            series_id=doc.series_id,
            volume_id=doc.volume_id,
            title=name,
            chapter_title=name,
            source_language=doc.source_language,
            series_order=doc.series_order,
        )
        db.add(new)
        db.flush()
        lines = [Line.document_id == doc.id, Line.line_number >= lo]
        anchored = [DocumentImage.document_id == doc.id, DocumentImage.anchor_position >= lo]
        if hi is not None:
            lines.append(Line.line_number < hi)
            anchored.append(DocumentImage.anchor_position < hi)
        db.execute(
            update(Line).where(*lines).values(document_id=new.id, line_number=Line.line_number - lo)
        )
        db.execute(
            update(Line)
            .where(Line.document_id == new.id, Line.line_number == 0)
            .values(prefix="%")
        )
        db.execute(
            update(DocumentImage)
            .where(*anchored)
            .values(document_id=new.id, anchor_position=DocumentImage.anchor_position - lo)
        )
        new_docs.append(new)

    at = siblings.index(doc) + 1
    renumber([*siblings[:at], *new_docs, *siblings[at:]])
    doc.updated_at = func.now()
    db.flush()
    db.expire_all()
    return [doc, *new_docs]
