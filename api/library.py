"""Queries shared by the documents, series, restructure, and transfer code."""

from fastapi import HTTPException, status
from sqlalchemy import and_, bindparam, func, inspect, or_, select, update
from sqlalchemy.orm import Session, attributes, object_session

from api.core.text import db_rows_to_arrays, lines_to_db_rows
from api.models import Document, Line, Series, Volume


def next_series_order(db: Session, series_id: int) -> int:
    """The slot after the series' last chapter."""
    return db.scalar(
        select(func.coalesce(func.max(Document.series_order), 0) + 1).where(
            Document.series_id == series_id
        )
    )


def reject_nul(*values: str) -> None:
    """422 for a NUL in a form-supplied string: Postgres text cannot hold it (else a 500)."""
    if any("\x00" in v for v in values):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "text must not contain NUL")


MAX_LINES = 50_000  # a 5 MiB file of "a\n" would otherwise become millions of ORM rows


def check_line_count(lines: list) -> None:
    """422 when a document would exceed MAX_LINES; call before building any rows."""
    if len(lines) > MAX_LINES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"too many lines (max {MAX_LINES})"
        )


def write_lines(db: Session, document_id: int, rows: list[dict]) -> None:
    """Insert ``lines_to_db_rows()`` output. Its blank-line prefix ``""`` is stored as
    ``"%"`` (the column holds % or $); ``line_arrays()`` turns it back into ``""``."""
    db.add_all(
        Line(
            document_id=document_id,
            line_number=row["line_number"],
            prefix=row["prefix"] or "%",
            raw_text=row["raw_text"],
            translated_text=row["translated_text"],
        )
        for row in rows
    )
    db.flush()


def line_arrays(db: Session, document_id: int) -> tuple[list[str], list[str]]:
    """(raw_lines, translated_lines) in the shape the ported text functions expect.

    A blank line comes back as ``""`` rather than ``"%"``, so the Markdown builders emit
    a paragraph break for it and a TXT export re-imports to the same lines."""
    rows = db.execute(
        select(Line.prefix, Line.raw_text, Line.translated_text)
        .where(Line.document_id == document_id)
        .order_by(Line.line_number)
    )
    return db_rows_to_arrays([
        {"line_number": i, "prefix": prefix if raw else "", "raw_text": raw,
         "translated_text": translated}
        for i, (prefix, raw, translated) in enumerate(rows)
    ])


def chapters(db: Session, series_id: int) -> list[Document]:
    """A series' chapters in reading order (ties broken by id, as the desktop does)."""
    return list(
        db.scalars(
            select(Document)
            .where(Document.series_id == series_id)
            .order_by(Document.series_order, Document.id)
        )
    )


_QUIET_ORDER = (
    update(Document.__table__)
    .where(Document.__table__.c.id == bindparam("b_id"))
    # An explicit SET of updated_at keeps its onupdate=now() from firing.
    .values(series_order=bindparam("b_order"), updated_at=Document.__table__.c.updated_at)
)


def renumber(docs: list[Document]) -> None:
    """Give ``docs`` series_order 1..N in list order (the caller flushes).

    A new number alone is not an edit: a stored chapter with no other pending change is
    renumbered in SQL with its updated_at kept, and its object updated to match."""
    quiet: list[dict] = []
    for order, doc in enumerate(docs, start=1):
        if doc.series_order == order:
            continue
        state = inspect(doc)
        if state.persistent and not state.modified:
            quiet.append({"b_id": doc.id, "b_order": order})
            attributes.set_committed_value(doc, "series_order", order)
        else:
            doc.series_order = order
    if quiet:
        object_session(docs[0]).execute(_QUIET_ORDER, quiet)


def arrange(db: Session, series: Series) -> list[Document]:
    """Keep each volume a contiguous run of series_order, in volume_order (chapters with no
    volume come last), numbered 1..N. A syosetu series keeps its own numbering. The caller
    flushes. Returns the chapters in final order."""
    docs = chapters(db, series.id)
    if series.syosetu_url:
        return docs
    rank = {
        vid: i
        for i, vid in enumerate(
            db.scalars(
                select(Volume.id)
                .where(Volume.series_id == series.id)
                .order_by(Volume.volume_order, Volume.id)
            )
        )
    }
    # stable; a volume's Illustrations chapter leads it
    docs.sort(key=lambda d: (rank.get(d.volume_id, len(rank)), not d.is_illustrations))
    renumber(docs)
    return docs


def chapter_numbers(docs: list[Document], syosetu: set[int]) -> dict[int, int | None]:
    """Display chapter numbers: series_order, less the Illustrations chapters before it
    (a syosetu series keeps its own numbering); None for an Illustrations chapter."""
    out: dict[int, int | None] = {}
    skipped: dict[int, int] = {}
    for doc in sorted(docs, key=lambda d: (d.series_id, d.series_order, d.id)):
        if doc.is_illustrations:
            out[doc.id] = None
            skipped[doc.series_id] = skipped.get(doc.series_id, 0) + 1
        elif doc.series_id in syosetu:
            out[doc.id] = doc.series_order
        else:
            out[doc.id] = doc.series_order - skipped.get(doc.series_id, 0)
    return out


def chapter_number(db: Session, doc: Document) -> int | None:
    """One chapter's display number (see ``chapter_numbers``)."""
    if doc.is_illustrations:
        return None
    if db.scalar(select(Series.syosetu_url).where(Series.id == doc.series_id)):
        return doc.series_order
    before = db.scalar(
        select(func.count()).where(
            Document.series_id == doc.series_id,
            Document.is_illustrations,
            Document.series_order < doc.series_order,
        )
    )
    return doc.series_order - before


def first_chapter_number(db: Session, volume_id: int) -> int | None:
    """The series-wide number of a volume's first chapter (Illustrations not counted),
    published or not; None when the volume has none."""
    doc = db.scalar(
        select(Document)
        .where(Document.volume_id == volume_id, Document.is_illustrations.is_(False))
        .order_by(Document.series_order, Document.id)
        .limit(1)
    )
    return None if doc is None else chapter_number(db, doc)


def volume_position(db: Session, doc: Document) -> int | None:
    """A chapter's 1-based place among its volume's chapters, Illustration chapters not
    counted; None for a loose chapter or an Illustrations chapter."""
    if doc.volume_id is None or doc.is_illustrations:
        return None
    before = db.scalar(
        select(func.count()).where(
            Document.volume_id == doc.volume_id,
            Document.is_illustrations.is_(False),
            or_(
                Document.series_order < doc.series_order,
                and_(Document.series_order == doc.series_order, Document.id < doc.id),
            ),
        )
    )
    return before + 1


def previous_chapter(db: Session, doc: Document) -> Document | None:
    """The chapter before ``doc``: in a syosetu series the one numbered exactly one less,
    elsewhere the nearest earlier chapter that is not an Illustrations chapter."""
    q = select(Document).where(Document.series_id == doc.series_id)
    if db.scalar(select(Series.syosetu_url).where(Series.id == doc.series_id)):
        q = q.where(Document.series_order == doc.series_order - 1).order_by(Document.id)
    else:
        q = q.where(
            Document.series_order < doc.series_order, Document.is_illustrations.is_(False)
        ).order_by(Document.series_order.desc(), Document.id.desc())
    return db.scalar(q.limit(1))


def send_to_volume_end(
    db: Session, series: Series, docs: list[Document], volume_id: int | None
) -> None:
    """Put ``docs`` at the end of a volume, in the caller's list order (assign_documents
    passes them in reading order); a syosetu series changes only volume_id. The caller
    flushes."""
    if not series.syosetu_url:
        top = next_series_order(db, series.id)
        for offset, doc in enumerate(docs):
            doc.series_order = top + offset
    for doc in docs:
        doc.volume_id = volume_id
    arrange(db, series)


def replace_raw_lines(db: Session, doc: Document, raw: list[str], force: bool) -> None:
    """Replace a document's source lines. Translations and translated_at stay attached
    by position, so a change in line count is refused (409) unless forced."""
    check_line_count(raw)
    rows = lines_to_db_rows(raw, [])
    existing = {
        line.line_number: line
        for line in db.scalars(select(Line).where(Line.document_id == doc.id))
    }
    if existing and len(rows) != len(existing) and not force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"line count changes from {len(existing)} to {len(rows)}; translations stay "
            "attached by line position",
        )
    for row in rows:
        line = existing.pop(row["line_number"], None)
        prefix = row["prefix"] or "%"
        if line is None:
            db.add(
                Line(
                    document_id=doc.id,
                    line_number=row["line_number"],
                    prefix=prefix,
                    raw_text=row["raw_text"],
                    translated_text="",
                )
            )
        else:
            line.prefix, line.raw_text = prefix, row["raw_text"]
    for line in existing.values():
        db.delete(line)
    doc.updated_at = func.now()
    db.flush()
