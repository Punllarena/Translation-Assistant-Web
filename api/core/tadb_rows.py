"""Row importers: desktop ta.db tables -> ORM objects, one SAVEPOINT per row."""

import sqlite3
from collections.abc import Callable

from sqlalchemy import inspect, select
from sqlalchemy.exc import DataError, IntegrityError
from sqlalchemy.orm import Session

from api.core.tadb_glossary import (
    DesktopProfile,
    adopt_profile,
    import_parse_chars,
    keep_unused,
    read_profiles,
)
from api.core.tadb_lines import BATCH, insert_lines
from api.core.tadb_schema import (
    NO_UNLOCK_OVERRIDE,
    ImportReport,
    _get,
    _parse_tristate_flag,
    _parse_ts,
    _skip,
)
from api.core.tadb_volumes import _volume_meta, find_or_add_volume
from api.models import Document, DocumentImage, Series, Volume

# The same caps every other import path enforces (api/library.py MAX_LINES, image uploads
# in api/routers/volumes.py): a browser upload is user input now, not an operator's CLI file.
MAX_LINES = 50_000
MAX_IMAGE_BYTES = 10 * 1024 * 1024
# Per text field (titles, lines, glossary, paths): every column is unbounded Text, and a
# desktop value is a sentence or a name, never this long.
MAX_TEXT_CHARS = 100_000


class Progress:
    """Cumulative count over documents, lines and images, so one rate covers the run."""

    def __init__(self, total: int, verb: str, cb: Callable[[int, int, str], None] | None):
        self.done, self.total, self.verb, self.cb = 0, total, verb, cb

    def step(self, n: int, phase: str) -> None:
        self.done += n
        if self.cb:
            self.cb(self.done, self.total, f"{self.verb} {phase}")


def _import_all(
    conn: sqlite3.Connection, db: Session, user_id: int, report: ImportReport,
    progress: Progress,
) -> None:
    profiles = read_profiles(conn, report)
    used: set[str] = set()  # desktop profiles copied to a series this import created
    series_by_title = _import_series(conn, db, user_id, report, profiles, used)
    _import_documents(conn, db, user_id, report, series_by_title, progress, profiles, used)
    keep_unused(db, user_id, profiles, used, report)
    import_parse_chars(db, user_id, profiles, report)


def _too_long(values: dict, table: str, label: str, report: ImportReport) -> bool:
    for key, value in values.items():
        if isinstance(value, str) and len(value) > MAX_TEXT_CHARS:
            _skip(report, table, label, f"{key} longer than {MAX_TEXT_CHARS} characters")
            return True
    return False


def _add(db: Session, obj: object, table: str, label: str, report: ImportReport) -> bool:
    """Insert one row in a SAVEPOINT; on a schema rejection skip and report it."""
    values = {a.key: getattr(obj, a.key) for a in inspect(obj).mapper.column_attrs}
    if _too_long(values, table, label, report):
        return False
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


def _import_series(
    conn: sqlite3.Connection,
    db: Session,
    user_id: int,
    report: ImportReport,
    profiles: dict[str, DesktopProfile],
    used: set[str],
) -> dict[str, Series]:
    meta: dict[str, sqlite3.Row] = {
        r["series_title"]: r for r in conn.execute("SELECT * FROM series_profiles")
    }
    # Series come from documents AND series_profiles: a series with no chapters
    # yet still carries the user's profile name, source URL and WordPress slug.
    titles = [
        r[0]
        for r in conn.execute(
            "SELECT series_title FROM documents WHERE series_title IS NOT NULL "
            "AND series_title != '' UNION SELECT series_title FROM series_profiles "
            "WHERE series_title IS NOT NULL AND series_title != ''"
        )
    ]
    out: dict[str, Series] = {}
    for title in titles:
        series = db.scalar(select(Series).where(Series.user_id == user_id, Series.title == title))
        if series is None:
            m = meta.get(title)
            # Column names are the desktop's: series_slug / series_title_short,
            # not the wp_-prefixed names this schema uses for them.
            unlock = _get(m, "series_profiles", "wp_unlock_after") if m else None
            series = Series(
                user_id=user_id,
                title=title,
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
            pname = (_get(m, "series_profiles", "profile_name", "") if m else "") or ""
            adopt_profile(db, series, pname, profiles, used, report)
        out[title] = series
    return out


def _own_series(
    db: Session, user_id: int, title: str, cache: dict[str, Series | None],
    report: ImportReport, label: str, created: set[int],
    on_create: Callable[[Series], None],
) -> Series | None:
    """The series a desktop chapter with no series_title lives in: one titled like the
    chapter, reused when the account has it, else created (its id goes into ``created``,
    and it is passed to ``on_create``)."""
    if title not in cache:
        series = db.scalar(select(Series).where(Series.user_id == user_id, Series.title == title))
        if series is None:
            series = Series(user_id=user_id, title=title)
            if _add(db, series, "series", repr(title), report):
                report.messages.append(
                    f"documents {label}: no series; created series {title!r}"
                )
                created.add(series.id)
                on_create(series)
            else:
                series = None
        cache[title] = series
    return cache[title]


def _import_documents(
    conn: sqlite3.Connection,
    db: Session,
    user_id: int,
    report: ImportReport,
    series_by_title: dict[str, Series],
    progress: Progress,
    profiles: dict[str, DesktopProfile],
    used: set[str],
) -> None:
    def adopt_fallback(series: Series) -> None:  # no series_profiles row: the fallback
        adopt_profile(db, series, "", profiles, used, report)

    volumes: dict[tuple, Volume | str | None] = {}
    id_map: dict[int, Document] = {}
    oneshots: dict[str, Series | None] = {}
    fresh: set[int] = set()  # oneshot series created by this import

    for row in conn.execute("SELECT * FROM documents"):
        progress.step(1, "chapters")
        label = f"row {row['id']}"
        series_title = _get(row, "documents", "series_title", "")
        vol_title = _get(row, "documents", "volume_title", "")
        series = series_by_title.get(series_title)
        if series_title and series is None:
            _skip(report, "documents", label, f"series {series_title!r} was not imported")
            continue
        if series is None:
            series = _own_series(
                db, user_id, row["title"], oneshots, report, label, fresh, adopt_fallback
            )
            if series is None:
                _skip(report, "documents", label, "its own series was not created")
                continue
        volume = None
        if vol_title:
            volume = find_or_add_volume(
                db, series, vol_title, volumes, report, _volume_meta(row), _add)
            if volume is None:
                _skip(report, "documents", label, f"volume {vol_title!r} was not imported")
                continue
        series_id = series.id
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
            # Alone in a series made for it, a chapter is chapter 1.
            series_order=1 if series_id in fresh else _get(row, "documents", "series_order", 0),
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

    line_counts: dict[int, int] = {}
    batch: list[tuple[str, dict]] = []
    for row in conn.execute("SELECT * FROM lines ORDER BY document_id, line_number"):
        progress.step(1, "lines")  # report() throttles, so per row is cheap
        doc = id_map.get(row["document_id"])
        if doc is None:
            _orphan(report, "lines", row, f"document_id {row['document_id']}")
            continue
        n = line_counts[doc.id] = line_counts.get(doc.id, 0) + 1
        if n > MAX_LINES:
            report.skipped["lines"] += 1
            if n == MAX_LINES + 1:  # one message per document, not one per skipped line
                report.messages.append(
                    f"documents {doc.title!r}: more than {MAX_LINES} lines; the rest were skipped"
                )
            continue
        prefix = _get(row, "lines", "prefix", "%")
        if not prefix:
            report.messages.append(f"lines row {row['id']}: empty prefix replaced with '%'")
            prefix = "%"
        label = f"row {row['id']}"
        values = {
            "document_id": doc.id,
            "line_number": row["line_number"],
            "prefix": prefix,
            "raw_text": row["raw_text"],
            "translated_text": _get(row, "lines", "translated_text", "") or "",
            "translated_at": _parse_ts(
                _get(row, "lines", "translated_at"), report, f"lines {label}"
            ),
        }
        if _too_long(values, "lines", label, report):
            continue
        batch.append((label, values))
        if len(batch) >= BATCH:
            insert_lines(db, batch, report)
            batch = []
    insert_lines(db, batch, report)

    for row in conn.execute("SELECT * FROM document_images"):
        progress.step(1, "images")
        doc = id_map.get(row["document_id"])
        if doc is None:
            _orphan(report, "document_images", row, f"document_id {row['document_id']}")
            continue
        if row["data"] is not None and len(row["data"]) > MAX_IMAGE_BYTES:
            _skip(report, "document_images", f"row {row['id']}",
                  f"image larger than {MAX_IMAGE_BYTES} bytes")
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
    progress.step(0, "images")  # the final count lands even with no images
