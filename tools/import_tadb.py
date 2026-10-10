"""One-shot importer: desktop ta.db (SQLite) -> ta-web (Postgres).

Reads a copy of the desktop database with the standard library and writes
through the ORM so every constraint applies. Profiles, series and volumes are
looked up and reused (a forced re-import adds chapters to the existing series);
documents are deduped on (user, series, title) so a forced re-import of a file
that has been worked in since adds only the new chapters. Each row is written in
its own SAVEPOINT: a row the schema rejects (duplicate, over-long value, orphan)
is skipped and reported, never silently dropped, and never aborts the run.
"""

import argparse
import hashlib
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import DataError, IntegrityError
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

# Every column name any released desktop schema has, transcribed from
# TranslationAssistant-PySide6-Port/translation_assistant/db.py (the _DDL constant
# plus the _apply_schema ALTER TABLE chain). A name absent from here is an
# importer bug, not a tolerable old file: _get refuses to read it.
SOURCE_COLUMNS: dict[str, frozenset[str]] = {
    "profiles": frozenset({"id", "name", "parse_chars", "created_at", "is_default"}),
    "glossary": frozenset({"id", "profile_id", "phrase", "translation", "sort_order"}),
    "custom_words": frozenset({"id", "profile_id", "word"}),
    "documents": frozenset({
        "id", "title", "source_language", "created_at", "updated_at", "last_position",
        "series_title", "series_order", "chapter_title", "volume_title", "volume_author",
        "volume_illustrator", "volume_publisher", "volume_identifier", "source_url",
        "wp_status", "wp_post_url", "wp_date", "wp_chapter_index",
    }),
    "lines": frozenset({
        "id", "document_id", "line_number", "prefix", "raw_text", "translated_text",
        "translated_at",
    }),
    "document_images": frozenset({
        "id", "document_id", "anchor_position", "is_cover", "src_path", "data",
        "exclude_export",
    }),
    "series_profiles": frozenset({
        "series_title", "profile_name", "syosetu_url", "series_slug", "series_title_short",
        "wp_password_enabled", "wp_unlock_after",
    }),
}

# The columns the desktop added by ALTER TABLE after the original DDL: a file written
# by an older build legitimately lacks them and _get's default stands in. Anything
# else the importer reads must be present, or the file is not a desktop ta.db.
OPTIONAL_COLUMNS: dict[str, frozenset[str]] = {
    "documents": frozenset({
        "series_title", "series_order", "chapter_title", "volume_title", "volume_author",
        "volume_illustrator", "volume_publisher", "volume_identifier", "source_url",
        "wp_status", "wp_post_url", "wp_date", "wp_chapter_index",
    }),
    "lines": frozenset({"translated_at"}),
    "document_images": frozenset({"exclude_export"}),
    "series_profiles": frozenset({
        "syosetu_url", "series_slug", "series_title_short", "wp_password_enabled",
        "wp_unlock_after",
    }),
}

# What this importer actually reads, per table: checked against the file up front so a
# missing non-optional column fails loudly before a single row is written.
READ_COLUMNS: dict[str, frozenset[str]] = {
    "profiles": frozenset({"id", "name", "parse_chars", "is_default"}),
    "glossary": frozenset({"id", "profile_id", "phrase", "translation", "sort_order"}),
    "custom_words": frozenset({"id", "profile_id", "word"}),
    "documents": frozenset({
        "id", "title", "source_language", "last_position", "series_title", "series_order",
        "chapter_title", "volume_title", "volume_author", "volume_illustrator",
        "volume_publisher", "volume_identifier", "source_url", "wp_status", "wp_post_url",
        "wp_date", "wp_chapter_index",
    }),
    "lines": frozenset({
        "id", "document_id", "line_number", "prefix", "raw_text", "translated_text",
        "translated_at",
    }),
    "document_images": frozenset({
        "id", "document_id", "anchor_position", "is_cover", "src_path", "data",
        "exclude_export",
    }),
    "series_profiles": frozenset({
        "series_title", "profile_name", "syosetu_url", "series_slug", "series_title_short",
        "wp_password_enabled", "wp_unlock_after",
    }),
}

# Desktop documents.<column> -> Volume attribute. The desktop keeps volume metadata
# denormalised on every chapter row; here it belongs to the volume.
VOLUME_META: dict[str, str] = {
    "epub_author": "volume_author",
    "epub_illustrator": "volume_illustrator",
    "epub_publisher": "volume_publisher",
    "epub_identifier": "volume_identifier",
}

# series_profiles.wp_unlock_after is NOT NULL DEFAULT -1, where -1 means "no series
# override, use the global setting"; the destination column is nullable, so -1 -> NULL.
NO_UNLOCK_OVERRIDE = -1


@dataclass
class ImportReport:
    written: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    skipped: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    # Rows deliberately not re-inserted because the account already has them. Not a
    # failure, so these never make the command exit non-zero.
    already_present: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    messages: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{k}: {v} written" for k, v in sorted(self.written.items())]
        parts += [f"{k}: {v} skipped" for k, v in sorted(self.skipped.items()) if v]
        parts += [
            f"{k}: {v} already present"
            for k, v in sorted(self.already_present.items())
            if v
        ]
        return "\n".join(parts)


def source_fingerprint(sqlite_path: Path) -> str:
    digest = hashlib.sha256()
    with open(sqlite_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def _get(row: sqlite3.Row, table: str, key: str, default=None):
    """Read a column that may legitimately be absent from an older ta.db.

    A ``key`` no released desktop schema has is a typo or an invented column, i.e. an
    importer bug that would otherwise yield ``default`` on every row in silence; it
    raises instead. Real absence (an older file lacking an ALTER-added column) still
    falls back to ``default`` — see OPTIONAL_COLUMNS.
    """
    if key not in SOURCE_COLUMNS[table]:
        raise RuntimeError(
            f"importer bug: {table}.{key} is not a column of any known desktop schema "
            f"(see SOURCE_COLUMNS, transcribed from the desktop db.py)"
        )
    # sqlite3.Row `in` tests values, not column names, so keys() is required.
    present = key in row.keys()  # noqa: SIM118
    return row[key] if present and row[key] is not None else default


def _check_source_schema(conn: sqlite3.Connection) -> None:
    """Fail before writing anything if the source is not a desktop ta.db."""
    for table, used in READ_COLUMNS.items():
        invented = sorted(used - SOURCE_COLUMNS[table])
        if invented:
            raise RuntimeError(
                f"importer bug: READ_COLUMNS[{table!r}] names {invented} which no known "
                "desktop schema has"
            )
        present = _columns(conn, table)
        if not present:
            raise RuntimeError(f"source database has no {table} table; not a desktop ta.db")
        missing = sorted(used - present - OPTIONAL_COLUMNS.get(table, frozenset()))
        if missing:
            raise RuntimeError(
                f"source {table} is missing column(s) {missing}; not a desktop ta.db"
            )


def _parse_ts(
    value: str | None, report: ImportReport, label: str, field_name: str = "translated_at"
) -> datetime | None:
    """Parse a desktop timestamp as UTC.

    The desktop writes these with SQLite's ``datetime('now')`` (UTC) and WordPress
    dates as ``...Z``, both without an offset in the first case. A naive value
    inserted into ``timestamptz`` would be reinterpreted in the server's session
    timezone, shifting every imported stamp, so UTC is attached explicitly.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        _skip(report, "timestamps", label, f"unparseable {field_name} {value!r}, left empty")
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _parse_tristate_flag(
    value: object, report: ImportReport, label: str
) -> bool | None:
    """series_profiles.wp_password_enabled is TEXT '1'/'0'/NULL (NULL = no override)."""
    if value is None or value == "":
        return None
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    report.messages.append(
        f"series {label}: wp_password_enabled {value!r} is not 1/0, treated as no override"
    )
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
    # The fingerprint only catches the *same* file. A ta.db the user kept working in
    # has a new fingerprint, so without this guard a second run would insert the whole
    # library again (containers are reused, documents are not).
    existing = db.scalar(select(func.count(Document.id)).where(Document.user_id == user_id)) or 0
    if existing and not (force or dry_run):
        raise RuntimeError(
            f"this account already has {existing} document(s); importing would duplicate "
            "the library. Pass force=True (--force) to import anyway: documents matching "
            "an existing series and title are then skipped, so only new chapters are added"
        )
    if existing and dry_run:
        # A dry run writes nothing, so it previews instead of refusing: that is the whole
        # point of the flag before committing to a second import.
        report.messages.append(
            f"this account already has {existing} document(s); a real import needs "
            "force=True (--force), and the chapters listed below as already present "
            "would be skipped"
        )

    conn = sqlite3.connect(sqlite_path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    _check_source_schema(conn)
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


def _skip(report: ImportReport, table: str, label: str, reason: str) -> None:
    report.skipped[table] += 1
    report.messages.append(f"{table} {label}: {reason}")


def _add(db: Session, obj: object, table: str, label: str, report: ImportReport) -> bool:
    """Insert one row in a SAVEPOINT; on a schema rejection skip and report it."""
    try:
        with db.begin_nested():
            db.add(obj)
    except (IntegrityError, DataError) as exc:
        # Only schema rejections are skippable; timeouts, deadlocks and dropped
        # connections (OperationalError etc.) propagate and abort the import.
        reason = str(exc.orig).splitlines()[0] if exc.orig else type(exc).__name__
        _skip(report, table, label, reason)
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
                parse_chars=_get(row, "profiles", "parse_chars", "、 。 ？ ！ 「 」 …… "),
                is_default=bool(_get(row, "profiles", "is_default", 0)),
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
            sort_order=_get(row, "glossary", "sort_order", 0),
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
    # Series come from documents AND series_profiles: a series with no chapters
    # yet still carries the user's profile link, source URL and WordPress slug.
    titles = [
        r[0]
        for r in conn.execute(
            "SELECT series_title FROM documents WHERE series_title IS NOT NULL "
            "AND series_title != '' UNION SELECT series_title FROM series_profiles "
            "WHERE series_title IS NOT NULL AND series_title != ''"
        )
    ]
    legacy_profiles = {r[0] for r in conn.execute("SELECT name FROM profiles")}
    out: dict[str, Series] = {}
    for title in titles:
        series = db.scalar(select(Series).where(Series.user_id == user_id, Series.title == title))
        if series is None:
            m = meta.get(title)
            pname = (_get(m, "series_profiles", "profile_name", "") if m else "") or ""
            profile = profiles_by_name.get(pname)
            if pname and profile is None:
                if pname in legacy_profiles:
                    _skip(report, "series", repr(title), f"its profile {pname!r} was not imported")
                    continue
                report.messages.append(
                    f"series {title!r}: profile {pname!r} does not exist in the source; no link"
                )
            # Column names are the desktop's: series_slug / series_title_short,
            # not the wp_-prefixed names this schema uses for them.
            unlock = _get(m, "series_profiles", "wp_unlock_after") if m else None
            series = Series(
                user_id=user_id,
                title=title,
                profile_id=profile.id if profile else None,
                syosetu_url=_get(m, "series_profiles", "syosetu_url", "") if m else "",
                wp_series_slug=_get(m, "series_profiles", "series_slug", "") if m else "",
                wp_series_title_short=(
                    _get(m, "series_profiles", "series_title_short", "") if m else ""
                ),
                wp_password_enabled=_parse_tristate_flag(
                    _get(m, "series_profiles", "wp_password_enabled") if m else None,
                    report,
                    repr(title),
                ),
                wp_unlock_after=None if unlock in (None, NO_UNLOCK_OVERRIDE) else unlock,
            )
            if not _add(db, series, "series", repr(title), report):
                continue
        out[title] = series
    return out


def _volume_meta(row: sqlite3.Row) -> dict[str, str]:
    return {
        attr: _get(row, "documents", column, "") or "" for attr, column in VOLUME_META.items()
    }


def _merge_volume_meta(volume: Volume, meta: dict[str, str], report: ImportReport) -> None:
    """First non-empty value wins; a later chapter that disagrees is reported."""
    for attr, value in meta.items():
        if not value:
            continue
        current = getattr(volume, attr) or ""
        if not current:
            setattr(volume, attr, value)
        elif current != value:
            report.messages.append(
                f"volumes {volume.title!r}: {attr} kept as {current!r}; another chapter "
                f"says {value!r}"
            )


def _volume(
    db: Session, series: Series, title: str, cache: dict[tuple[int, str], Volume | None],
    report: ImportReport, meta: dict[str, str],
) -> Volume | None:
    key = (series.id, title)
    if key not in cache:
        volume = db.scalar(
            select(Volume).where(Volume.series_id == series.id, Volume.title == title)
        )
        if volume is None:
            order = db.scalar(select(func.count(Volume.id)).where(Volume.series_id == series.id))
            volume = Volume(series_id=series.id, title=title, volume_order=order or 0, **meta)
            if not _add(db, volume, "volumes", repr(title), report):
                volume = None
        else:
            _merge_volume_meta(volume, meta, report)
        cache[key] = volume
    elif cache[key] is not None:
        _merge_volume_meta(cache[key], meta, report)
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
        label = f"row {row['id']}"
        series_title = _get(row, "documents", "series_title", "")
        vol_title = _get(row, "documents", "volume_title", "")
        series = series_by_title.get(series_title)
        if series_title and series is None:
            _skip(report, "documents", label, f"series {series_title!r} was not imported")
            continue
        volume = None
        if series and vol_title:
            volume = _volume(db, series, vol_title, volumes, report, _volume_meta(row))
            if volume is None:
                _skip(report, "documents", label, f"volume {vol_title!r} was not imported")
                continue
        elif vol_title:
            report.messages.append(f"documents {label}: volume_title {vol_title!r} has no series")
        series_id = series.id if series else None
        existing = db.scalar(
            select(Document).where(
                Document.user_id == user_id,
                Document.series_id == series_id,
                Document.title == row["title"],
            )
        )
        if existing is not None:
            # A forced re-import of a ta.db that has been worked in since: keep the
            # chapter already here (it may have newer translations) and add only new ones.
            report.already_present["documents"] += 1
            report.messages.append(
                f"documents {label}: {row['title']!r} is already in this account, kept as is"
            )
            continue
        doc = Document(
            user_id=user_id,
            series_id=series_id,
            volume_id=volume.id if volume else None,
            title=row["title"],
            chapter_title=_get(row, "documents", "chapter_title", ""),
            source_language=_get(row, "documents", "source_language", "ja"),
            series_order=_get(row, "documents", "series_order", 0),
            source_url=_get(row, "documents", "source_url", ""),
            last_position=_get(row, "documents", "last_position", 0),
            wp_status=_get(row, "documents", "wp_status", ""),
            wp_post_url=_get(row, "documents", "wp_post_url", ""),
            wp_chapter_index=_get(row, "documents", "wp_chapter_index"),
            wp_published_at=_parse_ts(
                _get(row, "documents", "wp_date"), report, f"documents {label}", "wp_date"
            ),
        )
        if _add(db, doc, "documents", f"row {row['id']}", report):
            id_map[row["id"]] = doc

    for row in conn.execute("SELECT * FROM lines ORDER BY document_id, line_number"):
        doc = id_map.get(row["document_id"])
        if doc is None:
            _orphan(report, "lines", row, f"document_id {row['document_id']}")
            continue
        prefix = _get(row, "lines", "prefix", "%")
        if not prefix:
            report.messages.append(f"lines row {row['id']}: empty prefix replaced with '%'")
            prefix = "%"
        line = Line(
            document_id=doc.id,
            line_number=row["line_number"],
            prefix=prefix,
            raw_text=row["raw_text"],
            translated_text=_get(row, "lines", "translated_text", "") or "",
            translated_at=_parse_ts(
                _get(row, "lines", "translated_at"), report, f"lines row {row['id']}"
            ),
        )
        _add(db, line, "lines", f"row {row['id']}", report)

    for row in conn.execute("SELECT * FROM document_images"):
        doc = id_map.get(row["document_id"])
        if doc is None:
            _orphan(report, "document_images", row, f"document_id {row['document_id']}")
            continue
        image = DocumentImage(
            document_id=doc.id,
            anchor_position=_get(row, "document_images", "anchor_position", 0),
            is_cover=bool(_get(row, "document_images", "is_cover", 0)),
            src_path=row["src_path"],
            data=row["data"],
            exclude_export=bool(_get(row, "document_images", "exclude_export", 0)),
        )
        _add(db, image, "document_images", f"row {row['id']}", report)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a desktop ta.db into ta-web")
    parser.add_argument("--db", required=True, type=Path, help="path to a copy of ta.db")
    parser.add_argument("--user", required=True, help="email of the destination account")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report counts, write nothing; allowed even when the account already has "
             "documents, so a second import can be inspected first",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="import even if this file was imported before or the account already has "
             "documents; chapters already present (same series and title) are skipped",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == args.user))
        if user is None:
            raise SystemExit(f"no such user: {args.user}")
        report = import_tadb(
            db, args.db, user.id, dry_run=args.dry_run, force=args.force
        )
        if args.dry_run:
            print("DRY RUN - nothing written")
        else:
            db.commit()
        print(report.summary())
        for message in report.messages:
            print(f"  ! {message}")
        if any(report.skipped.values()):
            raise SystemExit("incomplete: some rows were skipped (see messages above)")


if __name__ == "__main__":
    main()
