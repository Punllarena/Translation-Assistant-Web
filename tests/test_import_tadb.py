import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from api.core.tadb_import import ImportReport, import_tadb
from api.models import Document, DocumentImage, Line, Profile, Series, UserSetting, Volume
from tests.fixtures.tadb import DESKTOP_DDL
from tests.fixtures.tadb import add_chapter as _add_chapter
from tests.fixtures.tadb import desktop_db as _desktop_db


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
    assert volume.epub_illustrator == "Illustrator A"
    assert volume.epub_publisher == "Publisher A"
    assert volume.epub_identifier == "urn:isbn:1"


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
    from api.core.tadb_schema import _get

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
    # Deliberately non-ASCII: SQLite's COLLATE NOCASE folds ASCII only, while the
    # destination's lower() index (Postgres) folds Unicode, so our constraint is the
    # stricter one. 'Kitsune'/'kitsune' could never reach us — the desktop's own
    # UNIQUE(profile_id, word) COLLATE NOCASE rejects it at the source — but 'Öko'/'öko'
    # can, and then one of them must be skipped on import. Do not "simplify" to ASCII.
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
    import api.core.tadb_rows as mod

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


def test_a_seriesless_desktop_chapter_becomes_its_own_series(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE documents SET series_title = '', volume_title = '', title = 'Oneshot'")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.written["documents"] == 1 and not report.skipped.get("documents")
    assert report.written["series"] == 2  # 'My Series' plus 'Oneshot'
    series = db.query(Series).filter_by(user_id=user.id, title="Oneshot").one()
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert doc.series_id == series.id
    assert doc.series_order == 1  # the desktop's 7 would leave a gap in a one-chapter series
    assert any("no series" in m and "Oneshot" in m for m in report.messages)


def test_a_chapter_joining_an_existing_series_keeps_its_desktop_order(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE documents SET series_title = '', volume_title = '', title = 'Oneshot'")
    user = make_user()
    db.add(Series(user_id=user.id, title="Oneshot"))
    db.flush()
    import_tadb(db, path, user.id)
    assert db.query(Document).filter_by(user_id=user.id).one().series_order == 7


def test_a_reimported_oneshot_joins_its_existing_series(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE documents SET series_title = '', volume_title = '', title = 'Oneshot'")
    user = make_user()
    import_tadb(db, path, user.id)
    report = import_tadb(db, path, user.id, force=True)
    assert db.query(Series).filter_by(user_id=user.id, title="Oneshot").count() == 1
    assert db.query(Document).filter_by(user_id=user.id).count() == 1
    assert report.already_present["documents"] == 1


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
    real_execute = db.execute

    def flaky(stmt, *a, **kw):
        if getattr(getattr(stmt, "table", None), "name", None) == "lines":  # the line INSERT
            raise OperationalError("stmt", {}, Exception("statement timeout"))
        return real_execute(stmt, *a, **kw)

    monkeypatch.setattr(db, "execute", flaky)
    with pytest.raises(OperationalError):
        import_tadb(db, path, user.id)
    monkeypatch.setattr(db, "execute", real_execute)
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


def test_dry_run_into_a_non_empty_account_previews_instead_of_refusing(db, make_user, tmp_path):
    """A dry run writes nothing, so the refusal would only block the preview."""
    user = make_user()
    import_tadb(db, _desktop_db(tmp_path), user.id)
    changed = _desktop_db(tmp_path / "later")
    _add_chapter(changed, "Chapter 2")
    report = import_tadb(db, changed, user.id, dry_run=True)
    assert report.written["documents"] == 1  # Chapter 2 would be added
    assert report.already_present["documents"] == 1  # Chapter 1 would be skipped
    assert any("already has 1 document" in m for m in report.messages)
    assert any("Chapter 1" in m and "already in this account" in m for m in report.messages)
    assert db.query(Document).filter_by(user_id=user.id).count() == 1  # nothing written


def test_refusals_are_the_refused_subclass(db, make_user, tmp_path):
    from api.core.tadb_import import Refused
    user = make_user()
    path = _desktop_db(tmp_path)
    import_tadb(db, path, user.id)
    with pytest.raises(Refused, match="already imported"):
        import_tadb(db, path, user.id)


def test_lines_beyond_the_per_document_cap_are_skipped_and_reported(
    db, make_user, tmp_path, monkeypatch
):
    import api.core.tadb_rows as rows

    monkeypatch.setattr(rows, "MAX_LINES", 1)  # the fixture chapter has two lines
    user = make_user()
    report = import_tadb(db, _desktop_db(tmp_path), user.id)
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert db.query(Line).filter_by(document_id=doc.id).count() == 1
    assert report.skipped["lines"] == 1
    assert sum("more than 1 lines" in m for m in report.messages) == 1


def test_oversized_images_are_skipped_and_reported(db, make_user, tmp_path, monkeypatch):
    import api.core.tadb_rows as rows

    monkeypatch.setattr(rows, "MAX_IMAGE_BYTES", 2)  # the fixture cover is 3 bytes
    user = make_user()
    report = import_tadb(db, _desktop_db(tmp_path), user.id)
    assert db.query(DocumentImage).count() == 0
    assert report.skipped["document_images"] == 1
    assert any("larger than 2 bytes" in m for m in report.messages)


def test_oversized_text_fields_are_skipped_in_every_table(db, make_user, tmp_path, monkeypatch):
    import api.core.tadb_rows as rows

    monkeypatch.setattr(rows, "MAX_TEXT_CHARS", 5)
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE lines SET raw_text = 'abcdefgh' WHERE line_number = 0")
    user = make_user()
    report = import_tadb(db, path, user.id)
    doc = db.query(Document).filter_by(user_id=user.id).one_or_none()
    # "Chapter 1" is 9 chars: the document itself is skipped, so are its lines
    assert doc is None
    assert report.skipped["documents"] == 1
    assert any("longer than 5 characters" in m for m in report.messages)


def test_a_bad_line_skips_only_itself_in_its_batch(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE lines SET raw_text = 'a' || char(0) || 'b' WHERE id = 1")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.skipped["lines"] == 1
    assert [m for m in report.messages if m.startswith("lines row 1:")]
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert db.query(Line).filter_by(document_id=doc.id).count() == 1
    assert report.written["lines"] == 1


def test_progress_counts_every_document_line_and_image(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    conn = sqlite3.connect(path)
    total = sum(conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ("documents", "lines", "document_images"))
    conn.close()
    calls = []
    import_tadb(db, path, make_user().id, on_progress=lambda *c: calls.append(c))
    assert calls[-1] == (total, total, "Importing images")
    assert [c[0] for c in calls] == sorted(c[0] for c in calls)
    assert {c[2] for c in calls} <= {"Importing chapters", "Importing lines", "Importing images"}
