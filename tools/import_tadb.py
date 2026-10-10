"""One-shot importer: desktop ta.db (SQLite) -> ta-web (Postgres).

Reads a copy of the desktop database with the standard library and writes
through the ORM so every constraint applies. Profiles, series and volumes are
looked up and reused (a forced re-import adds chapters to the existing series);
documents, lines and images are inserted on every run. Each row is written in
its own SAVEPOINT: a row the schema rejects (duplicate, over-long value, orphan)
is skipped and reported, never silently dropped, and never aborts the run.
"""

import argparse
import hashlib
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import (
    CustomWord,
    Document,
    DocumentImage,
    GlossaryEntry,
    Line,
    Profile,
    Series,
    User,
    UserSetting,
    Volume,
)

FINGERPRINT_KEY = "imported_tadb_fingerprints"


@dataclass
class ImportReport:
    written: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    messages: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{k}: {v} written" for k, v in sorted(self.written.items())]
        parts += [f"{k}: {v} skipped" for k, v in sorted(self.skipped.items()) if v]
        return "\n".join(parts)


def source_fingerprint(sqlite_path: Path) -> str:
    digest = hashlib.sha256()
    with open(sqlite_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _get(row: sqlite3.Row, key: str, default=None):
    """Read a column that may not exist in an older ta.db."""
    # sqlite3.Row `in` tests values, not column names, so keys() is required.
    present = key in row.keys()  # noqa: SIM118
    return row[key] if present and row[key] is not None else default


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
) -> ImportReport:
    sqlite_path = Path(sqlite_path)
    report = ImportReport()
    fingerprint = source_fingerprint(sqlite_path)
    setting_row, seen = _fingerprints(db, user_id)
    if fingerprint in seen and not force:
        raise RuntimeError(
            f"{sqlite_path} was already imported for this user; pass force=True to import again"
        )

    conn = sqlite3.connect(f"file:{sqlite_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    # One SAVEPOINT around the whole import: a dry run rolls back only this work,
    # never the caller's transaction.
    savepoint = db.begin_nested()
    try:
        _import_all(conn, db, user_id, report)
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


def _import_all(
    conn: sqlite3.Connection, db: Session, user_id: int, report: ImportReport
) -> None:
    profiles_by_name = _import_profiles(conn, db, user_id, report)
    series_by_title = _import_series(conn, db, user_id, report, profiles_by_name)
    _import_documents(conn, db, user_id, report, series_by_title)


def _add(db: Session, obj: object, table: str, label: str, report: ImportReport) -> bool:
    """Insert one row in a SAVEPOINT; on a schema rejection skip and report it."""
    try:
        with db.begin_nested():
            db.add(obj)
    except DBAPIError as exc:
        report.skipped[table] += 1
        reason = str(exc.orig).splitlines()[0] if exc.orig else type(exc).__name__
        report.messages.append(f"{table} {label}: {reason}")
        return False
    report.written[table] += 1
    return True


def _orphan(report: ImportReport, table: str, row: sqlite3.Row, what: str) -> None:
    report.skipped[table] += 1
    report.messages.append(f"{table} row {row['id']}: {what} not found")


def _import_profiles(
    conn: sqlite3.Connection, db: Session, user_id: int, report: ImportReport
) -> dict[str, Profile]:
    by_name: dict[str, Profile] = {}
    by_old_id: dict[int, Profile] = {}
    for row in conn.execute("SELECT * FROM profiles"):
        profile = db.scalar(
            select(Profile).where(Profile.user_id == user_id, Profile.name == row["name"])
        )
        if profile is None:
            profile = Profile(
                user_id=user_id,
                name=row["name"],
                parse_chars=_get(row, "parse_chars", "、 。 ？ ！ 「 」 …… "),
                is_default=bool(_get(row, "is_default", 0)),
            )
            if not _add(db, profile, "profiles", f"row {row['id']}", report):
                continue
        by_name[row["name"]] = profile
        by_old_id[row["id"]] = profile

    for row in conn.execute("SELECT * FROM glossary"):
        profile = by_old_id.get(row["profile_id"])
        if profile is None:
            _orphan(report, "glossary", row, f"profile_id {row['profile_id']}")
            continue
        entry = GlossaryEntry(
            profile_id=profile.id,
            phrase=row["phrase"],
            translation=row["translation"],
            sort_order=_get(row, "sort_order", 0),
        )
        _add(db, entry, "glossary", f"row {row['id']}", report)

    for row in conn.execute("SELECT * FROM custom_words"):
        profile = by_old_id.get(row["profile_id"])
        if profile is None:
            _orphan(report, "custom_words", row, f"profile_id {row['profile_id']}")
            continue
        word = CustomWord(profile_id=profile.id, word=row["word"])
        _add(db, word, "custom_words", f"row {row['id']}", report)
    return by_name


def _import_series(
    conn: sqlite3.Connection,
    db: Session,
    user_id: int,
    report: ImportReport,
    profiles_by_name: dict[str, Profile],
) -> dict[str, Series]:
    meta: dict[str, sqlite3.Row] = {
        r["series_title"]: r for r in conn.execute("SELECT * FROM series_profiles")
    }
    titles = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT series_title FROM documents "
            "WHERE series_title IS NOT NULL AND series_title != ''"
        )
    ]
    out: dict[str, Series] = {}
    for title in titles:
        series = db.scalar(select(Series).where(Series.user_id == user_id, Series.title == title))
        if series is None:
            m = meta.get(title)
            profile = profiles_by_name.get(_get(m, "profile_name", "") if m else "")
            series = Series(
                user_id=user_id,
                title=title,
                profile_id=profile.id if profile else None,
                syosetu_url=_get(m, "syosetu_url", "") if m else "",
                wp_series_slug=_get(m, "wp_series_slug", "") if m else "",
                wp_series_title_short=_get(m, "wp_series_title_short", "") if m else "",
            )
            if not _add(db, series, "series", repr(title), report):
                continue
        out[title] = series
    return out


def _volume(
    db: Session, series: Series, title: str, cache: dict[tuple[int, str], Volume | None],
    report: ImportReport,
) -> Volume | None:
    key = (series.id, title)
    if key not in cache:
        volume = db.scalar(select(Volume).where(Volume.series_id == series.id, Volume.title == title))
        if volume is None:
            order = db.scalar(select(func.count(Volume.id)).where(Volume.series_id == series.id))
            volume = Volume(series_id=series.id, title=title, volume_order=order or 0)
            if not _add(db, volume, "volumes", repr(title), report):
                volume = None
        cache[key] = volume
    return cache[key]


def _import_documents(
    conn: sqlite3.Connection,
    db: Session,
    user_id: int,
    report: ImportReport,
    series_by_title: dict[str, Series],
) -> None:
    volumes: dict[tuple[int, str], Volume | None] = {}
    id_map: dict[int, Document] = {}

    for row in conn.execute("SELECT * FROM documents"):
        series = series_by_title.get(_get(row, "series_title", "") or "")
        vol_title = _get(row, "volume_title", "")
        volume = _volume(db, series, vol_title, volumes, report) if series and vol_title else None
        doc = Document(
            user_id=user_id,
            series_id=series.id if series else None,
            volume_id=volume.id if volume else None,
            title=row["title"],
            source_language=_get(row, "source_language", "ja"),
            series_order=_get(row, "series_order", 0),
            source_url=_get(row, "source_url", ""),
            last_position=_get(row, "last_position", 0),
            wp_post_id=_get(row, "wp_post_id"),
            wp_status=_get(row, "wp_status", ""),
        )
        if _add(db, doc, "documents", f"row {row['id']}", report):
            id_map[row["id"]] = doc

    for row in conn.execute("SELECT * FROM lines ORDER BY document_id, line_number"):
        doc = id_map.get(row["document_id"])
        if doc is None:
            _orphan(report, "lines", row, f"document_id {row['document_id']}")
            continue
        line = Line(
            document_id=doc.id,
            line_number=row["line_number"],
            prefix=_get(row, "prefix", "%") or "%",
            raw_text=row["raw_text"],
            translated_text=_get(row, "translated_text", "") or "",
            translated_at=_parse_ts(_get(row, "translated_at")),
        )
        _add(db, line, "lines", f"row {row['id']}", report)

    for row in conn.execute("SELECT * FROM document_images"):
        doc = id_map.get(row["document_id"])
        if doc is None:
            _orphan(report, "document_images", row, f"document_id {row['document_id']}")
            continue
        image = DocumentImage(
            document_id=doc.id,
            anchor_position=_get(row, "anchor_position", 0),
            is_cover=bool(_get(row, "is_cover", 0)),
            src_path=row["src_path"],
            data=row["data"],
            exclude_export=bool(_get(row, "exclude_export", 0)),
        )
        _add(db, image, "document_images", f"row {row['id']}", report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a desktop ta.db into ta-web")
    parser.add_argument("--db", required=True, type=Path, help="path to a copy of ta.db")
    parser.add_argument("--user", required=True, help="email of the destination account")
    parser.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    parser.add_argument("--force", action="store_true", help="import again even if seen before")
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.user))
        if user is None:
            raise SystemExit(f"no such user: {args.user}")
        report = import_tadb(
            db, args.db, user.id, dry_run=args.dry_run, force=args.force
        )
        if args.dry_run:
            print("DRY RUN — nothing written")
        else:
            db.commit()
        print(report.summary())
        for message in report.messages:
            print(f"  ! {message}")


if __name__ == "__main__":
    main()
