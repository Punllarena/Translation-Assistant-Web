"""Queries shared by the documents, series, restructure, and transfer code."""

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.text import db_rows_to_arrays, lines_to_db_rows
from api.models import Document, Line


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


def renumber(docs: list[Document]) -> None:
    """Give ``docs`` series_order 1..N in list order (the caller flushes)."""
    for order, doc in enumerate(docs, start=1):
        doc.series_order = order


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
