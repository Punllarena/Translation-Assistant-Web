"""Desktop ta.db schema knowledge and row parsing helpers."""

import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

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
    # Documents the account had before this run: a non-zero count means a real run
    # without force=True would be refused.
    existing_documents: int = 0

    def summary(self) -> str:
        parts = [f"{k}: {v} written" for k, v in sorted(self.written.items())]
        parts += [f"{k}: {v} skipped" for k, v in sorted(self.skipped.items()) if v]
        parts += [
            f"{k}: {v} already present"
            for k, v in sorted(self.already_present.items())
            if v
        ]
        return "\n".join(parts)


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


def _skip(report: ImportReport, table: str, label: str, reason: str) -> None:
    report.skipped[table] += 1
    report.messages.append(f"{table} {label}: {reason}")
