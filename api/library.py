"""Queries shared by the documents, series, restructure, and transfer code."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.text import db_rows_to_arrays
from api.models import Document, Line


def next_series_order(db: Session, series_id: int | None) -> int:
    """The slot after the series' last chapter; 0 for a document outside any series."""
    if series_id is None:
        return 0
    return db.scalar(
        select(func.coalesce(func.max(Document.series_order), 0) + 1).where(
            Document.series_id == series_id
        )
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


def renumber(docs: list[Document]) -> None:
    """Give ``docs`` series_order 1..N in list order (the caller flushes)."""
    for order, doc in enumerate(docs, start=1):
        doc.series_order = order
