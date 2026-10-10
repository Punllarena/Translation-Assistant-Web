import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from api.models import Document, DocumentImage, Line, Profile, Series, UserSetting, Volume
from tools.import_tadb import ImportReport, import_tadb

# Copied verbatim from the desktop app's source of truth,
# TranslationAssistant-PySide6-Port/translation_assistant/db.py: the `_DDL` constant
# (without its PRAGMAs, which SQLite applies per connection) ...
DESKTOP_DDL = """
CREATE TABLE IF NOT EXISTS profiles (
    id          INTEGER PRIMARY KEY,
    name        TEXT    UNIQUE NOT NULL,
    parse_chars TEXT    NOT NULL
                        DEFAULT '、 。 ？ ！ 「 」 …… ',
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    is_default  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS glossary (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    phrase      TEXT    NOT NULL,
    translation TEXT    NOT NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    UNIQUE(profile_id, phrase)
);

CREATE INDEX IF NOT EXISTS idx_glossary_profile ON glossary(profile_id, sort_order);

CREATE TABLE IF NOT EXISTS custom_words (
    id          INTEGER PRIMARY KEY,
    profile_id  INTEGER NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    word        TEXT    NOT NULL COLLATE NOCASE,
    UNIQUE(profile_id, word)
);

CREATE INDEX IF NOT EXISTS idx_words_profile ON custom_words(profile_id);

CREATE TABLE IF NOT EXISTS documents (
    id              INTEGER PRIMARY KEY,
    title           TEXT    NOT NULL,
    source_language TEXT    NOT NULL DEFAULT 'ja',
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    last_position   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS lines (
    id              INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    line_number     INTEGER NOT NULL,
    prefix          TEXT    NOT NULL DEFAULT '%',
    raw_text        TEXT    NOT NULL,
    translated_text TEXT    NOT NULL DEFAULT '',
    UNIQUE(document_id, line_number)
);

CREATE INDEX IF NOT EXISTS idx_lines_document ON lines(document_id, line_number);

CREATE TABLE IF NOT EXISTS document_images (
    id              INTEGER PRIMARY KEY,
    document_id     INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    anchor_position INTEGER NOT NULL DEFAULT 0,
    is_cover        INTEGER NOT NULL DEFAULT 0,
    src_path        TEXT    NOT NULL,
    data            BLOB    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_document_images_doc ON document_images(document_id, anchor_position);

CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS series_profiles (
    series_title TEXT PRIMARY KEY,
    profile_name TEXT NOT NULL DEFAULT ''
);
"""

# ... and the idempotent `ALTER TABLE` chain `Database._apply_schema` runs after it, in
# the same order. A ta.db written by an older desktop build has only a prefix of these,
# which is the tolerance `_get`/OPTIONAL_COLUMNS exists for.
DESKTOP_ALTERS = [
    "ALTER TABLE documents ADD COLUMN series_title TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN series_order INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE documents ADD COLUMN chapter_title TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_title TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_author TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_illustrator TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_publisher TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN volume_identifier TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN syosetu_url TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN series_slug TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN series_title_short TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE series_profiles ADD COLUMN wp_password_enabled TEXT DEFAULT NULL",
    "ALTER TABLE series_profiles ADD COLUMN wp_unlock_after INTEGER NOT NULL DEFAULT -1",
    "ALTER TABLE documents ADD COLUMN source_url TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE documents ADD COLUMN wp_status TEXT DEFAULT NULL",
    "ALTER TABLE documents ADD COLUMN wp_post_url TEXT DEFAULT NULL",
    "ALTER TABLE documents ADD COLUMN wp_date TEXT DEFAULT NULL",
    "ALTER TABLE documents ADD COLUMN wp_chapter_index INTEGER DEFAULT NULL",
    "ALTER TABLE lines ADD COLUMN translated_at TEXT DEFAULT NULL",
    "ALTER TABLE document_images ADD COLUMN exclude_export INTEGER NOT NULL DEFAULT 0",
]

# The columns an older build's file lacks, in the variant exercised below.
OLDER_BUILD_LACKS = ("translated_at", "volume_title", "exclude_export", "source_url")


def _desktop_db(tmp_path: Path, *, with_optional_columns: bool = True) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "ta.db"
    conn = sqlite3.connect(path)
    conn.executescript(DESKTOP_DDL)
    alters = DESKTOP_ALTERS
    if not with_optional_columns:
        alters = [
            a for a in DESKTOP_ALTERS if not any(c in a for c in OLDER_BUILD_LACKS)
        ]
        assert len(alters) == len(DESKTOP_ALTERS) - len(OLDER_BUILD_LACKS)
    for statement in alters:
        conn.execute(statement)
    conn.execute("INSERT INTO profiles (name, parse_chars, is_default) VALUES ('wn', '。！', 1)")
    sp_cols = "series_title, profile_name, syosetu_url, series_slug, series_title_short"
    sp_vals = "('My Series', 'wn', 'https://ncode.syosetu.com/n0000a/', 'my-series', 'MS')"
    if with_optional_columns:
        sp_cols += ", wp_password_enabled, wp_unlock_after"
        sp_vals = (
            "('My Series', 'wn', 'https://ncode.syosetu.com/n0000a/', 'my-series', 'MS', '1', 3)"
        )
    conn.execute(f"INSERT INTO series_profiles ({sp_cols}) VALUES {sp_vals}")
    cols = (
        "title, series_title, series_order, chapter_title, wp_status, last_position, "
        "wp_post_url, wp_date, wp_chapter_index"
    )
    vals = (
        "('Chapter 1', 'My Series', 7, 'Chapter 1 - The Start', 'publish', 3, "
        "'https://blog/ch1', '2024-05-06T07:08:09Z', 11)"
    )
    if with_optional_columns:
        cols += ", volume_title, volume_author, volume_illustrator, volume_publisher, " \
                "volume_identifier, source_url"
        vals = vals[:-1] + (
            ", 'Volume 1', 'Author A', 'Illustrator A', 'Publisher A', 'urn:isbn:1', "
            "'https://src/1')"
        )
    conn.execute(f"INSERT INTO documents ({cols}) VALUES {vals}")
    line_cols = "document_id, line_number, prefix, raw_text, translated_text"
    stamp = ", translated_at" if with_optional_columns else ""
    sval = ", '2024-05-06 07:08:09'" if with_optional_columns else ""
    conn.execute(
        f"INSERT INTO lines ({line_cols}{stamp}) VALUES (1, 0, '%', '一行目', 'Line one'{sval})"
    )
    conn.execute(f"INSERT INTO lines ({line_cols}) VALUES (1, 1, '$', '二行目', '')")
    excl = ", exclude_export" if with_optional_columns else ""
    eval_ = ", 1" if with_optional_columns else ""
    conn.execute(
        f"INSERT INTO document_images (document_id, anchor_position, is_cover, src_path, data"
        f"{excl}) VALUES (1, 5, 1, 'cover.jpg', X'FFD8FF'{eval_})"
    )
    conn.commit()
    conn.close()
    return path


def _add_chapter(path: Path, title: str, *, series: str = "My Series") -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO documents (title, series_title, series_order, volume_title) "
        "VALUES (?, ?, 9, 'Volume 1')",
        (title, series),
    )
    doc_id = conn.execute("SELECT id FROM documents WHERE title = ?", (title,)).fetchone()[0]
    conn.execute(
        "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text) "
        "VALUES (?, 0, '%', '新しい行', 'A new line')",
        (doc_id,),
    )
    conn.commit()
    conn.close()


def test_import_loads_the_whole_library(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _desktop_db(tmp_path), user.id)
    assert isinstance(report, ImportReport)
    assert report.written["documents"] == 1
    assert report.written["lines"] == 2
    assert report.written["series"] == 1

    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.title == "My Series"
    assert series.syosetu_url == "https://ncode.syosetu.com/n0000a/"
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert doc.series_id == series.id
    assert doc.volume_id is not None
    lines = db.query(Line).filter_by(document_id=doc.id).order_by(Line.line_number).all()
    assert [row.raw_text for row in lines] == ["一行目", "二行目"]
    assert lines[0].translated_text == "Line one"
    image = db.query(DocumentImage).filter_by(document_id=doc.id).one()
    assert image.is_cover is True and image.exclude_export is True
    assert image.anchor_position == 5 and image.src_path == "cover.jpg"
    assert bytes(image.data) == b"\xff\xd8\xff"
    assert doc.series_order == 7 and doc.wp_status == "publish"
    assert doc.last_position == 3 and doc.source_url == "https://src/1"
    assert doc.chapter_title == "Chapter 1 - The Start"
    assert doc.wp_post_url == "https://blog/ch1" and doc.wp_chapter_index == 11
    assert doc.wp_published_at == datetime(2024, 5, 6, 7, 8, 9, tzinfo=UTC)
    assert lines[0].prefix == "%" and lines[1].prefix == "$"
    # Asserted against a fixed UTC, never against the stored value's own tzinfo:
    # the desktop writes datetime('now'), which is UTC without an offset.
    assert lines[0].translated_at == datetime(2024, 5, 6, 7, 8, 9, tzinfo=UTC)
    assert lines[1].translated_at is None
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["wn"]


def test_wordpress_and_volume_metadata_land_in_the_schema(db, make_user, tmp_path):
    """The desktop column names are series_slug / series_title_short / volume_*."""
    user = make_user()
    import_tadb(db, _desktop_db(tmp_path), user.id)
    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.wp_series_slug == "my-series"
    assert series.wp_series_title_short == "MS"
    assert series.wp_password_enabled is True
    assert series.wp_unlock_after == 3
    volume = db.query(Volume).filter_by(series_id=series.id).one()
    assert volume.epub_author == "Author A"
    assert volume.illustrator == "Illustrator A"
    assert volume.publisher == "Publisher A"
    assert volume.identifier == "urn:isbn:1"


def test_unlock_after_sentinel_becomes_null(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE series_profiles SET wp_unlock_after = -1, wp_password_enabled = NULL")
    user = make_user()
    import_tadb(db, path, user.id)
    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.wp_unlock_after is None
    assert series.wp_password_enabled is None


def test_disagreeing_volume_metadata_keeps_the_first_and_reports(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(
        path,
        "INSERT INTO documents (title, series_title, volume_title, volume_author) "
        "VALUES ('Chapter 2', 'My Series', 'Volume 1', 'Someone Else')",
    )
    user = make_user()
    report = import_tadb(db, path, user.id)
    volume = db.query(Volume).one()
    assert volume.epub_author == "Author A"
    assert any("Someone Else" in m and "kept as" in m for m in report.messages)


def test_a_column_no_desktop_schema_has_is_an_error_not_a_default(db, make_user, tmp_path):
    """The bug this guard exists for: wp_post_id never existed in ta.db."""
    from tools.import_tadb import _get

    conn = sqlite3.connect(_desktop_db(tmp_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM documents").fetchone()
    conn.close()
    assert _get(row, "documents", "wp_post_url", "") == "https://blog/ch1"
    with pytest.raises(RuntimeError, match="wp_post_id"):
        _get(row, "documents", "wp_post_id")


def test_a_source_missing_a_required_column_is_refused(db, make_user, tmp_path):
    path = tmp_path / "ta.db"
    conn = sqlite3.connect(path)
    conn.executescript(DESKTOP_DDL)
    conn.execute("ALTER TABLE documents DROP COLUMN last_position")
    conn.commit()
    conn.close()
    user = make_user()
    with pytest.raises(RuntimeError, match="last_position"):
        import_tadb(db, path, user.id)


def test_a_source_without_the_expected_tables_is_refused(db, make_user, tmp_path):
    path = tmp_path / "not-ta.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE unrelated (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    user = make_user()
    with pytest.raises(RuntimeError, match="not a desktop ta.db"):
        import_tadb(db, path, user.id)


def test_dry_run_writes_nothing(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _desktop_db(tmp_path), user.id, dry_run=True)
    assert report.written["documents"] == 1
    assert db.query(Document).filter_by(user_id=user.id).count() == 0
    assert db.query(Series).filter_by(user_id=user.id).count() == 0
    assert db.query(Profile).filter_by(user_id=user.id).count() == 0
    assert db.query(UserSetting).filter_by(user_id=user.id).count() == 0


def test_second_run_on_the_same_file_is_refused(db, make_user, tmp_path):
    user = make_user()
    path = _desktop_db(tmp_path)
    import_tadb(db, path, user.id)
    with pytest.raises(RuntimeError, match="already imported"):
        import_tadb(db, path, user.id)
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_force_allows_a_second_run_without_duplicating_chapters(db, make_user, tmp_path):
    user = make_user()
    path = _desktop_db(tmp_path)
    import_tadb(db, path, user.id)
    report = import_tadb(db, path, user.id, force=True)
    assert db.query(Document).filter_by(user_id=user.id).count() == 1
    assert report.already_present["documents"] == 1
    assert not report.skipped["documents"]
    assert "already present" in report.summary()


def test_import_into_a_non_empty_account_is_refused_without_force(db, make_user, tmp_path):
    """A ta.db worked in since the first import has a new fingerprint, so only the
    document count stands between the user and a duplicated library."""
    user = make_user()
    import_tadb(db, _desktop_db(tmp_path), user.id)
    changed = _desktop_db(tmp_path / "later")
    _add_chapter(changed, "Chapter 2")
    with pytest.raises(RuntimeError, match="already has 1 document"):
        import_tadb(db, changed, user.id)
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_forced_reimport_of_a_changed_file_adds_only_the_new_chapter(db, make_user, tmp_path):
    user = make_user()
    import_tadb(db, _desktop_db(tmp_path), user.id)
    changed = _desktop_db(tmp_path / "later")
    _add_chapter(changed, "Chapter 2")
    report = import_tadb(db, changed, user.id, force=True)
    assert report.written["documents"] == 1
    assert report.already_present["documents"] == 1
    titles = sorted(d.title for d in db.query(Document).filter_by(user_id=user.id))
    assert titles == ["Chapter 1", "Chapter 2"]
    assert db.query(Series).filter_by(user_id=user.id).count() == 1
    assert db.query(Volume).count() == 1


def test_dry_run_does_not_record_the_fingerprint(db, make_user, tmp_path):
    user = make_user()
    path = _desktop_db(tmp_path)
    import_tadb(db, path, user.id, dry_run=True)
    import_tadb(db, path, user.id)  # must not raise
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_older_database_without_optional_columns_imports(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _desktop_db(tmp_path, with_optional_columns=False), user.id)
    assert report.written["documents"] == 1
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert doc.volume_id is None
    assert doc.source_url == ""
    assert doc.series_order == 7
    assert db.query(Line).filter_by(document_id=doc.id).first().translated_at is None
    image = db.query(DocumentImage).filter_by(document_id=doc.id).one()
    assert image.exclude_export is False and image.anchor_position == 5


def test_rows_failing_validation_are_reported_not_dropped_silently(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO lines (document_id, line_number, prefix, raw_text) "
                 "VALUES (999, 0, '%', 'orphan')")
    conn.commit()
    conn.close()
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.skipped["lines"] == 1
    assert any("999" in m for m in report.messages)


def test_fingerprint_is_recorded_in_user_settings(db, make_user, tmp_path):
    user = make_user()
    import_tadb(db, _desktop_db(tmp_path), user.id)
    row = db.query(UserSetting).filter_by(
        user_id=user.id, key="imported_tadb_fingerprints"
    ).one()
    assert isinstance(row.value_json, list) and len(row.value_json) == 1


def test_force_reuses_existing_containers_and_adds_chapters(db, make_user, tmp_path):
    user = make_user()
    path = _desktop_db(tmp_path)
    first = import_tadb(db, path, user.id)
    changed = _desktop_db(tmp_path / "later")
    _add_chapter(changed, "Chapter 2")
    second = import_tadb(db, changed, user.id, force=True)
    assert first.written["series"] == 1 and first.written["volumes"] == 1
    assert second.written["series"] == 0 and second.written["volumes"] == 0
    assert second.written["profiles"] == 0
    assert db.query(Series).filter_by(user_id=user.id).count() == 1
    assert db.query(Profile).filter_by(user_id=user.id).count() == 1
    docs = db.query(Document).filter_by(user_id=user.id).all()
    assert len(docs) == 2
    assert len({d.series_id for d in docs}) == 1 and len({d.volume_id for d in docs}) == 1


def test_case_variant_custom_words_and_overlong_values_are_skipped(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    conn = sqlite3.connect(path)
    # SQLite's COLLATE NOCASE folds ASCII only, so a real ta.db can hold this pair
    # while the destination's lower() index (Postgres, full Unicode) rejects it.
    conn.execute("INSERT INTO custom_words (profile_id, word) VALUES (1, 'Öko')")
    conn.execute("INSERT INTO custom_words (profile_id, word) VALUES (1, 'öko')")
    conn.execute("INSERT INTO custom_words (profile_id, word) VALUES (1, ?)", ("x" * 500,))
    conn.execute("INSERT INTO lines (document_id, line_number, prefix, raw_text) "
                 "VALUES (1, 2, '%%', 'bad prefix')")
    conn.commit()
    conn.close()
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.written["custom_words"] == 1
    assert report.skipped["custom_words"] == 2
    assert report.skipped["lines"] == 1
    assert report.written["lines"] == 2
    assert len(report.messages) == 3


def _tweak(path: Path, *statements: str) -> None:
    conn = sqlite3.connect(path)
    for stmt in statements:
        conn.execute(stmt)
    conn.commit()
    conn.close()


def test_series_without_documents_is_imported(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO series_profiles (series_title, profile_name, syosetu_url) "
                 "VALUES ('Empty', 'wn', 'https://ncode.syosetu.com/n1/')")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.written["series"] == 2
    empty = db.query(Series).filter_by(user_id=user.id, title="Empty").one()
    assert empty.syosetu_url == "https://ncode.syosetu.com/n1/" and empty.profile_id is not None


def test_document_of_a_skipped_series_is_skipped_not_detached(
    db, make_user, tmp_path, monkeypatch
):
    import tools.import_tadb as mod

    real_add = mod._add

    def reject_series(db_, obj, table, label, report):
        if isinstance(obj, Series):
            mod._skip(report, table, label, "rejected by test")
            return False
        return real_add(db_, obj, table, label, report)

    monkeypatch.setattr(mod, "_add", reject_series)
    user = make_user()
    report = import_tadb(db, _desktop_db(tmp_path), user.id)
    assert report.skipped["series"] == 1
    assert report.skipped["documents"] == 1 and report.written["documents"] == 0
    assert db.query(Document).filter_by(user_id=user.id).count() == 0
    assert any("documents" in m and "not imported" in m for m in report.messages)


def test_document_without_a_series_title_still_imports_standalone(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE documents SET series_title = '', volume_title = ''")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.written["documents"] == 1 and not report.skipped.get("documents")
    assert db.query(Document).filter_by(user_id=user.id).one().series_id is None


def test_skipped_profile_skips_its_series_and_chapters(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    long_name = "p" * 200
    _tweak(path, f"UPDATE profiles SET name = '{long_name}'",
           f"UPDATE series_profiles SET profile_name = '{long_name}'")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.skipped["profiles"] == 1
    assert report.skipped["series"] == 1
    assert report.skipped["documents"] == 1
    assert any("profile" in m and "not imported" in m for m in report.messages)


def test_transient_database_errors_abort_instead_of_being_skipped(
    db, make_user, tmp_path, monkeypatch
):
    from sqlalchemy.exc import OperationalError

    user = make_user()
    path = _desktop_db(tmp_path)
    real_add = db.add

    def flaky(obj, *a, **kw):
        if isinstance(obj, Line):
            raise OperationalError("stmt", {}, Exception("statement timeout"))
        return real_add(obj, *a, **kw)

    monkeypatch.setattr(db, "add", flaky)
    with pytest.raises(OperationalError):
        import_tadb(db, path, user.id)
    monkeypatch.setattr(db, "add", real_add)
    assert db.query(Document).filter_by(user_id=user.id).count() == 0
    assert db.query(UserSetting).filter_by(user_id=user.id).count() == 0
    import_tadb(db, path, user.id)  # not refused: nothing was recorded


def test_bad_timestamp_and_empty_prefix_are_reported(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE lines SET translated_at = 'yesterday-ish' WHERE id = 1",
           "UPDATE lines SET prefix = '' WHERE id = 2")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.skipped["timestamps"] == 1
    assert any("yesterday-ish" in m and "translated_at" in m for m in report.messages)
    assert any("empty prefix" in m for m in report.messages)
    doc = db.query(Document).filter_by(user_id=user.id).one()
    stored = db.query(Line).filter_by(document_id=doc.id).order_by(Line.line_number)
    prefixes = [x.prefix for x in stored]
    assert prefixes == ["%", "%"]
