"""One-shot importer: desktop ta.db (SQLite) -> ta-web (Postgres).

Reads a copy of the desktop database with the standard library and writes
through the ORM so every constraint applies. Profiles, series and volumes are
looked up and reused (a forced re-import adds chapters to the existing series);
documents are deduped on (user, series, title) so a forced re-import of a file
that has been worked in since adds only the new chapters. Each row is written in
its own SAVEPOINT: a row the schema rejects (duplicate, over-long value, orphan)
is skipped and reported, never silently dropped, and never aborts the run.
"""

import hashlib
import sqlite3
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.tadb_rows import Progress, _import_all
from api.core.tadb_schema import ImportReport, _check_source_schema
from api.models import Document, UserSetting

__all__ = ["ImportReport", "Refused", "import_tadb"]

FINGERPRINT_KEY = "imported_tadb_fingerprints"


class Refused(RuntimeError):
    """A refusal force=True overrides: the file was imported before (existing == 0), or
    the account already has `existing` documents."""

    def __init__(self, message: str, *, existing: int = 0) -> None:
        super().__init__(message)
        self.existing = existing


def not_empty_preview(existing: int) -> str:
    """The message a dry run into a non-empty account adds (CLI wording)."""
    return (
        f"this account already has {existing} document(s); a real import needs "
        "force=True (--force), and the chapters listed below as already present "
        "would be skipped"
    )


def source_fingerprint(sqlite_path: Path) -> str:
    digest = hashlib.sha256()
    with open(sqlite_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _fingerprints(db: Session, user_id: int) -> tuple[UserSetting | None, list[str]]:
    row = db.scalar(
        select(UserSetting).where(
            UserSetting.user_id == user_id, UserSetting.key == FINGERPRINT_KEY
        )
    )
    return row, list(row.value_json) if row and isinstance(row.value_json, list) else []


def import_tadb(
    db: Session,
    sqlite_path: Path,
    user_id: int,
    *,
    dry_run: bool = False,
    force: bool = False,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> ImportReport:
    sqlite_path = Path(sqlite_path)
    report = ImportReport()
    fingerprint = source_fingerprint(sqlite_path)
    setting_row, seen = _fingerprints(db, user_id)
    if fingerprint in seen and not force:
        raise Refused(
            f"{sqlite_path} was already imported for this user; pass force=True to import again"
        )
    # The fingerprint only catches the *same* file. A ta.db the user kept working in
    # has a new fingerprint, so without this guard a second run would insert the whole
    # library again (containers are reused, documents are not).
    existing = db.scalar(select(func.count(Document.id)).where(Document.user_id == user_id)) or 0
    if existing and not (force or dry_run):
        raise Refused(
            f"this account already has {existing} document(s); importing would duplicate "
            "the library. Pass force=True (--force) to import anyway: documents matching "
            "an existing series and title are then skipped, so only new chapters are added",
            existing=existing,
        )
    report.existing_documents = existing
    if existing and dry_run:
        # A dry run writes nothing, so it previews instead of refusing: that is the whole
        # point of the flag before committing to a second import.
        report.messages.append(not_empty_preview(existing))

    conn = sqlite3.connect(sqlite_path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    _check_source_schema(conn)
    total = sum(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ("documents", "lines", "document_images"))
    progress = Progress(total, "Checking" if dry_run else "Importing", on_progress)
    # One SAVEPOINT around the whole import: a dry run rolls back only this work,
    # never the caller's transaction.
    savepoint = db.begin_nested()
    try:
        _import_all(conn, db, user_id, report, progress)
    except BaseException:
        savepoint.rollback()
        raise
    finally:
        conn.close()

    if dry_run:
        savepoint.rollback()
        return report
    savepoint.commit()

    if setting_row is None:
        db.add(
            UserSetting(user_id=user_id, key=FINGERPRINT_KEY, value_json=[fingerprint])
        )
    elif fingerprint not in seen:
        setting_row.value_json = [*seen, fingerprint]
    db.flush()
    return report
