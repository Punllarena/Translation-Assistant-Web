import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from api.core.tadb_import import ImportReport, import_tadb
from api.models import (
    CustomWord,
    Document,
    DocumentImage,
    GlossaryEntry,
    Line,
    Series,
    UserSetting,
    Volume,
    VolumeCover,
)
from tests.fixtures.tadb import DESKTOP_DDL
from tests.fixtures.tadb import add_chapter as _add_chapter
from tests.fixtures.tadb import add_profile as _add_profile
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
    assert db.query(DocumentImage).filter_by(document_id=doc.id).count() == 0
    cover = db.query(VolumeCover).filter_by(volume_id=doc.volume_id).one()  # chapter → volume
    assert cover.src_path == "cover.jpg" and bytes(cover.data) == b"\xff\xd8\xff"
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
    assert "profiles" not in report.written


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
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO glossary (profile_id, phrase, translation) VALUES (1, '猫', 'Cat')",
           "INSERT INTO custom_words (profile_id, word) VALUES (1, 'Rimuru')")
    _add_profile(path, "spare", glossary=(("犬", "Dog"),))  # unused: kept as a series
    user = make_user()
    report = import_tadb(db, path, user.id, dry_run=True)
    assert report.written["documents"] == 1
    assert (report.written["series"], report.written["glossary"]) == (2, 2)
    assert (report.written["custom_words"], report.written["settings"]) == (1, 1)
    assert db.query(Document).filter_by(user_id=user.id).count() == 0
    assert db.query(Series).filter_by(user_id=user.id).count() == 0
    assert db.query(GlossaryEntry).count() == 0
    assert db.query(CustomWord).count() == 0
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
    # a cover on a chapter with no volume has no volume to go to: kept, excluded from export
    assert image.exclude_export is True and image.anchor_position == 5


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
    assert db.query(Series).filter_by(user_id=user.id).count() == 1
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
    assert empty.syosetu_url == "https://ncode.syosetu.com/n1/"


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


def test_tadb_volume_titles_are_parsed(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _add_chapter(path, "Chapter 2")
    _tweak(path, "INSERT INTO documents (title, series_title, series_order, volume_title) "
                 "VALUES ('Chapter 3', 'My Series', 10, 'Prologue')")
    _tweak(path, "INSERT INTO documents (title, series_title, series_order, volume_title) "
                 "VALUES ('Chapter 4', 'My Series', 11, 'Volume 99999999')")
    user = make_user()
    import_tadb(db, path, user.id)
    vols = db.query(Volume).order_by(Volume.volume_order).all()
    assert [(v.kind, v.volume_index and int(v.volume_index), v.subtitle) for v in vols] == [
        ("Volume", 1, ""), ("", None, "Prologue"), ("", None, "Volume 99999999")]
    again = import_tadb(db, path, user.id, force=True)
    assert db.query(Volume).count() == 3
    assert again.written["volumes"] == 0


def test_tadb_two_titles_naming_one_volume_are_reported(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO documents (title, series_title, series_order, volume_title) "
                 "VALUES ('Chapter 3', 'My Series', 10, 'Vol 3')")
    _tweak(path, "INSERT INTO documents (title, series_title, series_order, volume_title) "
                 "VALUES ('Chapter 4', 'My Series', 11, 'Volume 3')")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert db.query(Volume).filter(Volume.volume_index == 3).count() == 1
    assert any("'Volume 3'" in m and "'Vol 3'" in m and "'Volume 3': merged into 'Volume 3'"
               in m for m in report.messages)


# --- desktop profiles: copied into series, never imported as rows -------------------------


def _glossary(db, series):
    rows = db.query(GlossaryEntry).filter_by(series_id=series.id).order_by(GlossaryEntry.sort_order)
    return [(g.phrase, g.translation, g.sort_order) for g in rows]


def _words(db, series):
    return sorted(w.word for w in db.query(CustomWord).filter_by(series_id=series.id))


def _series(db, user, title):
    return db.query(Series).filter_by(user_id=user.id, title=title).one()


def test_shared_profile_copied_to_each_new_series(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _add_profile(path, "shared", glossary=(("太郎", "Taro"), ("花子", "Hanako")), words=("Rimuru",))
    _tweak(path, "UPDATE series_profiles SET profile_name = 'shared'",
           "INSERT INTO series_profiles (series_title, profile_name) VALUES ('Sequel', 'shared')")
    user = make_user()
    report = import_tadb(db, path, user.id)
    for title in ("My Series", "Sequel"):
        series = _series(db, user, title)
        assert _glossary(db, series) == [("太郎", "Taro", 0), ("花子", "Hanako", 1)]
        assert _words(db, series) == ["Rimuru"]
        word = db.query(CustomWord).filter_by(series_id=series.id).one()
        assert word.user_id == user.id
    assert (report.written["glossary"], report.written["custom_words"]) == (4, 2)
    assert db.query(CustomWord).filter_by(user_id=user.id, series_id=None).count() == 0


def test_series_without_profile_name_gets_default_profile(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO glossary (profile_id, phrase, translation) VALUES (1, '猫', 'Cat')",
           "UPDATE profiles SET is_default = 0")
    _add_profile(path, "main", glossary=(("犬", "Dog"),), is_default=True)
    _tweak(path, "UPDATE series_profiles SET profile_name = ''",
           "INSERT INTO series_profiles (series_title) VALUES ('Unlinked')",
           "UPDATE documents SET series_title = '', volume_title = '', title = 'Oneshot'")
    user = make_user()
    import_tadb(db, path, user.id)
    for title in ("My Series", "Unlinked", "Oneshot"):
        assert _glossary(db, _series(db, user, title)) == [("犬", "Dog", 0)], title
    # 'wn' went to no series and is not empty: it is kept as a series of its own
    assert _glossary(db, _series(db, user, "wn")) == [("猫", "Cat", 0)]


def test_without_a_default_the_oldest_profile_is_the_fallback(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE profiles SET is_default = 0",
           "INSERT INTO glossary (profile_id, phrase, translation) VALUES (1, '猫', 'Cat')",
           "UPDATE series_profiles SET profile_name = ''")
    _add_profile(path, "later", glossary=(("犬", "Dog"),))
    user = make_user()
    import_tadb(db, path, user.id)
    assert _glossary(db, _series(db, user, "My Series")) == [("猫", "Cat", 0)]


def test_missing_profile_name_imports_with_empty_glossary_and_message(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO glossary (profile_id, phrase, translation) VALUES (1, '猫', 'Cat')",
           "UPDATE series_profiles SET profile_name = 'gone'")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert _glossary(db, _series(db, user, "My Series")) == []
    assert report.written["documents"] == 1 and not report.skipped.get("series")
    assert any("'gone'" in m and "My Series" in m for m in report.messages)


def test_parse_chars_set_only_when_unset_and_not_default(db, make_user, tmp_path):
    def parse_chars(user):
        row = db.query(UserSetting).filter_by(user_id=user.id, key="parse_chars").one_or_none()
        return row.value_json if row else None

    fresh = make_user(email="fresh@example.com")
    import_tadb(db, _desktop_db(tmp_path / "a"), fresh.id)
    assert parse_chars(fresh) == "。！"  # the desktop default profile's

    keeps = make_user(email="keeps@example.com")
    db.add(UserSetting(user_id=keeps.id, key="parse_chars", value_json=""))
    db.flush()
    import_tadb(db, _desktop_db(tmp_path / "b"), keeps.id)
    assert parse_chars(keeps) == ""

    plain = make_user(email="plain@example.com")
    path = _desktop_db(tmp_path / "c")
    _tweak(path, "UPDATE profiles SET parse_chars = '、 。 ？ ！ 「 」 …… '")
    import_tadb(db, path, plain.id)
    assert parse_chars(plain) is None


def test_existing_series_untouched(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO glossary (profile_id, phrase, translation) VALUES (1, '猫', 'Cat')",
           "INSERT INTO series_profiles (series_title, profile_name) VALUES ('New', 'wn')")
    user = make_user()
    existing = Series(user_id=user.id, title="My Series")
    db.add(existing)
    db.flush()
    db.add(GlossaryEntry(series_id=existing.id, phrase="猫", translation="Neko", sort_order=0))
    db.flush()
    import_tadb(db, path, user.id)
    assert _glossary(db, existing) == [("猫", "Neko", 0)]
    assert _glossary(db, _series(db, user, "New")) == [("猫", "Cat", 0)]
    assert db.query(Series).filter_by(user_id=user.id).count() == 2  # 'wn' was used


@pytest.mark.parametrize(
    ("taken", "expected"),
    [((), "default"), (("Default",), "default (glossary)"),
     (("default", "DEFAULT (glossary)"), "default (glossary 2)")],
)
def test_reimport_keeps_unused_profile_as_series(db, make_user, tmp_path, taken, expected):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE profiles SET is_default = 0")
    _add_profile(path, "default", glossary=(("猫", "Cat"),), words=("Rimuru",), is_default=True)
    user = make_user()
    db.add(Series(user_id=user.id, title="My Series"))  # every desktop series already exists
    db.add_all(Series(user_id=user.id, title=t) for t in taken)
    db.flush()
    report = import_tadb(db, path, user.id)
    kept = _series(db, user, expected)
    assert _glossary(db, kept) == [("猫", "Cat", 0)] and _words(db, kept) == ["Rimuru"]
    assert db.query(Document).filter_by(series_id=kept.id).count() == 0
    assert any(repr(expected) in m for m in report.messages)
    # My Series, the taken titles and the kept profile; the empty 'wn' is dropped
    assert db.query(Series).filter_by(user_id=user.id).count() == 2 + len(taken)


def test_forced_reimport_does_not_duplicate_glossary_series(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO glossary (profile_id, phrase, translation) VALUES (1, '猫', 'Cat')")
    _add_profile(path, "other", glossary=(("犬", "Dog"),), words=("Rimuru",))
    user = make_user()
    first = import_tadb(db, path, user.id)
    titles = sorted(s.title for s in db.query(Series).filter_by(user_id=user.id))
    assert titles == ["My Series", "other"] and not first.already_present.get("series")
    for _ in range(2):
        again = import_tadb(db, path, user.id, force=True)
        # 'wn' matches My Series (its copy), 'other' its own glossary-only series
        assert again.already_present["series"] == 2
        assert not again.written.get("series")
    assert sorted(s.title for s in db.query(Series).filter_by(user_id=user.id)) == titles
    assert _glossary(db, _series(db, user, "other")) == [("犬", "Dog", 0)]


def test_unused_profile_skipped_when_a_series_matches_ignoring_word_case(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "UPDATE profiles SET is_default = 0")
    _add_profile(path, "default", glossary=(("猫", "Cat"),), words=("Rimuru",), is_default=True)
    user = make_user()
    db.add(Series(user_id=user.id, title="My Series"))
    same = Series(user_id=user.id, title="Same")
    db.add(same)
    db.flush()
    db.add(GlossaryEntry(series_id=same.id, phrase="猫", translation="Cat", sort_order=5))
    db.add(CustomWord(user_id=user.id, series_id=same.id, word="RIMURU"))
    db.flush()
    report = import_tadb(db, path, user.id)
    # pairs and lower(word) are equal, so the profile is already present
    assert report.already_present["series"] == 1
    assert db.query(Series).filter_by(user_id=user.id).count() == 2


def test_unused_empty_profile_dropped(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _add_profile(path, "empty")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert [s.title for s in db.query(Series).filter_by(user_id=user.id)] == ["My Series"]
    assert report.written["series"] == 1


def test_report_has_no_profiles_table(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _add_profile(path, "other", glossary=(("猫", "Cat"),))
    report = import_tadb(db, path, make_user().id)
    tables = set(report.written) | set(report.skipped) | set(report.already_present)
    assert "profiles" not in tables
    assert "profiles" not in report.summary()


def test_glossary_rows_of_a_missing_profile_are_reported(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _tweak(path, "INSERT INTO glossary (profile_id, phrase, translation) VALUES (99, 'a', 'b')")
    report = import_tadb(db, path, make_user().id)
    assert report.skipped["glossary"] == 1
    assert any("profile_id 99" in m for m in report.messages)


def test_a_later_cover_in_the_volume_stays_an_excluded_image(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _add_chapter(path, "Chapter 2")  # series_order 9, after chapter 1's 7, same volume
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO document_images (document_id, anchor_position, is_cover, src_path,"
                  " data, exclude_export) VALUES (2, 0, 1, 'later.jpg', X'FFD8FF', 0)")
    conn.commit()
    conn.close()
    user = make_user()
    import_tadb(db, path, user.id)
    later = db.query(DocumentImage).one()
    assert (later.src_path, later.exclude_export) == ("later.jpg", True)
    assert db.query(VolumeCover).one().src_path == "cover.jpg"


def _chapter0(path: Path, *, status: str = "publish") -> int:
    """A desktop chapter 0 of 'My Series' with two paragraphs and an image."""
    _tweak(
        path,
        "INSERT INTO documents (title, series_title, series_order, wp_status, wp_chapter_index) "
        f"VALUES ('Summary', 'My Series', 0, '{status}', 0)",
    )
    conn = sqlite3.connect(path)
    doc_id = conn.execute("SELECT id FROM documents WHERE title = 'Summary'").fetchone()[0]
    conn.close()
    _tweak(
        path,
        "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text) "
        f"VALUES ({doc_id}, 0, '%', 'あ', 'First para.')",
        "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text) "
        f"VALUES ({doc_id}, 1, '%', 'い', 'Second para.')",
        "INSERT INTO document_images (document_id, anchor_position, is_cover, src_path, data) "
        f"VALUES ({doc_id}, 0, 0, 'x.jpg', X'FFD8FF')",
    )
    return doc_id


def test_a_live_chapter_0_becomes_the_series_summary(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _chapter0(path)
    user = make_user()
    report = import_tadb(db, path, user.id)
    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.wp_summary == "First para.\n\nSecond para."
    assert series.wp_summary_pending is False
    assert [d.title for d in db.query(Document).filter_by(user_id=user.id)] == ["Chapter 1"]
    assert report.skipped["document_images"] == 1
    assert any("chapter 0 became the summary of 'My Series'" in m for m in report.messages)


def test_a_chapter_0_that_is_not_live_imports_as_a_chapter(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _chapter0(path, status="draft")
    user = make_user()
    import_tadb(db, path, user.id)
    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.wp_summary == ""
    titles = sorted(d.title for d in db.query(Document).filter_by(user_id=user.id))
    assert titles == ["Chapter 1", "Summary"]
    # Index 0 would make the chapter unpublishable (build_chapter refuses it).
    imported = db.query(Document).filter_by(user_id=user.id, title="Summary").one()
    assert imported.wp_chapter_index is None


def test_a_reimport_keeps_an_edited_summary(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _chapter0(path)
    user = make_user()
    import_tadb(db, path, user.id)
    series = db.query(Series).filter_by(user_id=user.id).one()
    series.wp_summary = "Edited by hand."
    db.flush()
    report = import_tadb(db, path, user.id, force=True)
    db.refresh(series)
    assert series.wp_summary == "Edited by hand."
    assert any("kept the summary already on 'My Series'" in m for m in report.messages)


def test_dry_run_reports_the_summary_and_writes_nothing(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    _chapter0(path)
    user = make_user()
    report = import_tadb(db, path, user.id, dry_run=True)
    assert any("chapter 0 became the summary" in m for m in report.messages)
    assert db.query(Series).filter_by(user_id=user.id).count() == 0
    assert db.query(Document).filter_by(user_id=user.id).count() == 0


def _add_summary_line(path: Path, doc_id: int, number: int, text: str) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text) "
        "VALUES (?, ?, '%', 'x', ?)", (doc_id, number, text))
    conn.commit()
    conn.close()


def test_an_oversized_chapter_0_is_not_written_and_is_reported(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    doc_id = _chapter0(path)
    for i in range(3):  # three lines of 60,000 characters: each fits, together they do not
        _add_summary_line(path, doc_id, 10 + i, "a" * 60_000)
    user = make_user()
    report = import_tadb(db, path, user.id)
    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.wp_summary == ""
    assert any("longer than 100000 characters" in m for m in report.messages)


def test_a_nul_summary_line_is_dropped_without_aborting_the_import(db, make_user, tmp_path):
    path = _desktop_db(tmp_path)
    doc_id = _chapter0(path)
    _add_summary_line(path, doc_id, 10, "bad\x00line")
    _add_summary_line(path, doc_id, 11, "z" * 100_001)
    user = make_user()
    report = import_tadb(db, path, user.id)
    series = db.query(Series).filter_by(user_id=user.id).one()
    assert series.wp_summary == "First para." + chr(10) * 2 + "Second para."
    assert report.skipped["lines"] == 2
    assert sum("were skipped" in m for m in report.messages) == 1
    assert db.query(Document).filter_by(user_id=user.id).count() == 1
