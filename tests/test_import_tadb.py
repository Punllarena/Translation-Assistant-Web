import sqlite3
from pathlib import Path

import pytest

from api.models import Document, DocumentImage, Line, Profile, Series, UserSetting
from tools.import_tadb import ImportReport, import_tadb

LEGACY_DDL = """
CREATE TABLE profiles (id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
    parse_chars TEXT NOT NULL DEFAULT '。', created_at TEXT, is_default INTEGER DEFAULT 0);
CREATE TABLE glossary (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL,
    phrase TEXT NOT NULL, translation TEXT NOT NULL, sort_order INTEGER DEFAULT 0);
CREATE TABLE custom_words (id INTEGER PRIMARY KEY, profile_id INTEGER NOT NULL, word TEXT NOT NULL);
CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT NOT NULL,
    source_language TEXT DEFAULT 'ja', created_at TEXT, updated_at TEXT,
    last_position INTEGER DEFAULT 0, series_title TEXT DEFAULT '',
    series_order INTEGER DEFAULT 0, volume_title TEXT DEFAULT '',
    source_url TEXT DEFAULT '', wp_post_id INTEGER, wp_status TEXT DEFAULT '');
CREATE TABLE lines (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
    line_number INTEGER NOT NULL, prefix TEXT DEFAULT '%', raw_text TEXT NOT NULL,
    translated_text TEXT DEFAULT '', translated_at TEXT);
CREATE TABLE document_images (id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL,
    anchor_position INTEGER DEFAULT 0, is_cover INTEGER DEFAULT 0,
    src_path TEXT NOT NULL, data BLOB NOT NULL, exclude_export INTEGER DEFAULT 0);
CREATE TABLE series_profiles (series_title TEXT PRIMARY KEY, profile_name TEXT DEFAULT '',
    syosetu_url TEXT DEFAULT '', wp_series_slug TEXT DEFAULT '');
"""


def _legacy_db(tmp_path: Path, *, with_optional_columns: bool = True) -> Path:
    path = tmp_path / "ta.db"
    conn = sqlite3.connect(path)
    ddl = LEGACY_DDL
    if not with_optional_columns:
        ddl = (
            ddl.replace(", translated_at TEXT", "")
            .replace(", volume_title TEXT DEFAULT ''", "")
            .replace(", exclude_export INTEGER DEFAULT 0", "")
            .replace(", source_url TEXT DEFAULT ''", "")
        )
    conn.executescript(ddl)
    conn.execute("INSERT INTO profiles (name, parse_chars, is_default) VALUES ('wn', '。！', 1)")
    conn.execute("INSERT INTO series_profiles (series_title, profile_name, syosetu_url) "
                 "VALUES ('My Series', 'wn', 'https://ncode.syosetu.com/n0000a/')")
    cols = "title, series_title, series_order"
    vals = "('Chapter 1', 'My Series', 0)"
    if with_optional_columns:
        cols += ", volume_title"
        vals = "('Chapter 1', 'My Series', 0, 'Volume 1')"
    conn.execute(f"INSERT INTO documents ({cols}) VALUES {vals}")
    line_cols = "document_id, line_number, prefix, raw_text, translated_text"
    conn.execute(f"INSERT INTO lines ({line_cols}) VALUES (1, 0, '%', '一行目', 'Line one')")
    conn.execute(f"INSERT INTO lines ({line_cols}) VALUES (1, 1, '$', '二行目', '')")
    conn.execute(
        "INSERT INTO document_images (document_id, anchor_position, is_cover, src_path, data) "
        "VALUES (1, 0, 1, 'cover.jpg', X'FFD8FF')"
    )
    conn.commit()
    conn.close()
    return path


def test_import_loads_the_whole_library(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _legacy_db(tmp_path), user.id)
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
    assert [l.raw_text for l in lines] == ["一行目", "二行目"]
    assert lines[0].translated_text == "Line one"
    assert db.query(DocumentImage).filter_by(document_id=doc.id).one().is_cover is True
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["wn"]


def test_dry_run_writes_nothing(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _legacy_db(tmp_path), user.id, dry_run=True)
    assert report.written["documents"] == 1
    assert db.query(Document).filter_by(user_id=user.id).count() == 0


def test_second_run_on_the_same_file_is_refused(db, make_user, tmp_path):
    user = make_user()
    path = _legacy_db(tmp_path)
    import_tadb(db, path, user.id)
    with pytest.raises(RuntimeError, match="already imported"):
        import_tadb(db, path, user.id)
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_force_allows_a_second_run(db, make_user, tmp_path):
    user = make_user()
    path = _legacy_db(tmp_path)
    import_tadb(db, path, user.id)
    import_tadb(db, path, user.id, force=True)
    assert db.query(Document).filter_by(user_id=user.id).count() == 2


def test_dry_run_does_not_record_the_fingerprint(db, make_user, tmp_path):
    user = make_user()
    path = _legacy_db(tmp_path)
    import_tadb(db, path, user.id, dry_run=True)
    import_tadb(db, path, user.id)  # must not raise
    assert db.query(Document).filter_by(user_id=user.id).count() == 1


def test_older_database_without_optional_columns_imports(db, make_user, tmp_path):
    user = make_user()
    report = import_tadb(db, _legacy_db(tmp_path, with_optional_columns=False), user.id)
    assert report.written["documents"] == 1
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert doc.volume_id is None
    assert doc.source_url == ""
    assert db.query(Line).filter_by(document_id=doc.id).first().translated_at is None


def test_rows_failing_validation_are_reported_not_dropped_silently(db, make_user, tmp_path):
    path = _legacy_db(tmp_path)
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
    import_tadb(db, _legacy_db(tmp_path), user.id)
    row = db.query(UserSetting).filter_by(
        user_id=user.id, key="imported_tadb_fingerprints"
    ).one()
    assert isinstance(row.value_json, list) and len(row.value_json) == 1


def test_force_reuses_existing_containers_and_adds_chapters(db, make_user, tmp_path):
    user = make_user()
    path = _legacy_db(tmp_path)
    first = import_tadb(db, path, user.id)
    second = import_tadb(db, path, user.id, force=True)
    assert first.written["series"] == 1 and first.written["volumes"] == 1
    assert second.written["series"] == 0 and second.written["volumes"] == 0
    assert second.written["profiles"] == 0
    assert db.query(Series).filter_by(user_id=user.id).count() == 1
    assert db.query(Profile).filter_by(user_id=user.id).count() == 1
    docs = db.query(Document).filter_by(user_id=user.id).all()
    assert len({d.series_id for d in docs}) == 1 and len({d.volume_id for d in docs}) == 1


def test_case_variant_custom_words_and_overlong_values_are_skipped(db, make_user, tmp_path):
    path = _legacy_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO custom_words (profile_id, word) VALUES (1, 'Kitsune')")
    conn.execute("INSERT INTO custom_words (profile_id, word) VALUES (1, 'kitsune')")
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
