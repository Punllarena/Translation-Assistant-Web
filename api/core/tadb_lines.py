"""Batched line inserts for the ta.db import: the bulk of a library (480k rows in a real one).

One SAVEPOINT per batch of Core INSERTs instead of one per ORM row. A batch the schema
rejects is retried row by row, so a bad row is still skipped and reported by its label
and never aborts the run; other errors (timeouts, dropped connections) propagate.
"""

from sqlalchemy import insert
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from api.core.tadb_schema import ImportReport, _skip
from api.models import Line

BATCH = 1000


def _reason(exc: IntegrityError | DataError) -> str:
    return str(exc.orig).splitlines()[0] if exc.orig else type(exc).__name__


def insert_lines(db: Session, batch: list[tuple[str, dict]], report: ImportReport) -> None:
    """Insert `batch` ((label, Line column values) pairs), counting into report."""
    if not batch:
        return
    try:
        with db.begin_nested():
            db.execute(insert(Line), [values for _, values in batch])
        report.written["lines"] += len(batch)
        return
    except (IntegrityError, DataError):
        pass
    for label, values in batch:
        try:
            with db.begin_nested():
                db.execute(insert(Line).values(**values))
        except (IntegrityError, DataError) as exc:
            _skip(report, "lines", label, _reason(exc))
            continue
        report.written["lines"] += 1
