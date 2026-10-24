"""ta.db chapters that share a title, and what a skipped chapter's lines and images report."""

import sqlite3
from pathlib import Path

from api.core.tadb_import import import_tadb
from api.models import Document, Line
from tests.fixtures.tadb import desktop_db


def _chapter(path: Path, title: str, *, volume: str = "Volume 1", url: str = "",
             order: int = 9) -> None:
    conn = sqlite3.connect(path)
    cur = conn.execute(
        "INSERT INTO documents (title, series_title, series_order, volume_title, source_url) "
        "VALUES (?, 'My Series', ?, ?, ?)",
        (title, order, volume, url),
    )
    conn.execute(
        "INSERT INTO lines (document_id, line_number, prefix, raw_text, translated_text) "
        "VALUES (?, 0, '%', '新しい行', '')",
        (cur.lastrowid,),
    )
    conn.commit()
    conn.close()


def _titles(db, user_id: int) -> list[str]:
    return sorted(d.title for d in db.query(Document).filter_by(user_id=user_id))


def test_a_title_repeated_in_another_volume_is_a_new_chapter(db, make_user, tmp_path):
    path = desktop_db(tmp_path)
    _chapter(path, "Afterword", volume="Volume 1")
    _chapter(path, "Afterword", volume="Volume 2")
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.written["documents"] == 3 and not report.already_present.get("documents")
    assert _titles(db, user.id) == ["Afterword", "Afterword", "Chapter 1"]
    assert report.written["lines"] == 4


def test_a_title_repeated_with_another_source_url_is_a_new_chapter(db, make_user, tmp_path):
    path = desktop_db(tmp_path)
    _chapter(path, "Chapter 1", url="https://src/2")  # same volume and title as row 1
    user = make_user()
    report = import_tadb(db, path, user.id)
    assert report.written["documents"] == 2 and not report.already_present.get("documents")
    assert not any("already in this account" in m for m in report.messages)


def test_a_reimported_chapter_is_matched_by_its_source_url(db, make_user, tmp_path):
    user = make_user()
    import_tadb(db, desktop_db(tmp_path), user.id)
    changed = desktop_db(tmp_path / "later")
    conn = sqlite3.connect(changed)
    conn.execute("UPDATE documents SET title = 'Chapter 1 (renamed)', volume_title = 'Volume 2'")
    conn.commit()
    conn.close()
    report = import_tadb(db, changed, user.id, force=True)
    assert report.already_present["documents"] == 1 and not report.written.get("documents")
    assert _titles(db, user.id) == ["Chapter 1"]


def test_a_chapter_without_url_matches_by_volume_and_title(db, make_user, tmp_path):
    user = make_user()
    first = desktop_db(tmp_path)
    _chapter(first, "Afterword", volume="Volume 1")
    import_tadb(db, first, user.id)
    changed = desktop_db(tmp_path / "later")
    _chapter(changed, "Afterword", volume="Volume 1")  # already here
    _chapter(changed, "Afterword", volume="Volume 2")  # new
    report = import_tadb(db, changed, user.id, force=True)
    assert report.already_present["documents"] == 2  # Chapter 1 and Volume 1's Afterword
    assert report.written["documents"] == 1
    assert _titles(db, user.id) == ["Afterword", "Afterword", "Chapter 1"]


def test_a_skipped_chapters_lines_and_images_are_reported_once(db, make_user, tmp_path):
    user = make_user()
    path = desktop_db(tmp_path)
    import_tadb(db, path, user.id)
    report = import_tadb(db, path, user.id, force=True)
    assert report.skipped["lines"] == 2 and report.skipped["document_images"] == 1
    assert not any("not found" in m for m in report.messages)
    about_row_1 = [m for m in report.messages if m.startswith("documents row 1:")]
    assert len(about_row_1) == 2  # "already in this account" and the lines/images it took along
    assert "2 lines and 1 image" in about_row_1[1]
    doc = db.query(Document).filter_by(user_id=user.id).one()
    assert db.query(Line).filter_by(document_id=doc.id).count() == 2


def test_a_line_whose_chapter_is_missing_from_the_file_is_still_not_found(
    db, make_user, tmp_path
):
    path = desktop_db(tmp_path)
    conn = sqlite3.connect(path)
    conn.execute("INSERT INTO lines (document_id, line_number, prefix, raw_text) "
                 "VALUES (999, 0, '%', 'orphan')")
    conn.commit()
    conn.close()
    report = import_tadb(db, path, user_id=make_user().id)
    assert any("document_id 999 not found" in m for m in report.messages)
