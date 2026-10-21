"""The data step of the volume-naming revision, run inside the test transaction against a
re-added ``title`` column; the db fixture rolls everything back."""

import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from api.models import Document

_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _migration():
    (path,) = _VERSIONS.glob("*_volume_naming.py")
    spec = importlib.util.spec_from_file_location("mig_volume_naming", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy(db):
    """The table as it was before the revision: a title, no unique naming indexes."""
    db.execute(text("ALTER TABLE volumes ADD COLUMN title text"))
    db.execute(text("DROP INDEX uq_volumes_kind_index"))
    db.execute(text("DROP INDEX uq_volumes_kind_subtitle"))


def _insert(db, series_id, title, order, epub_title=""):
    return db.execute(text(
        "INSERT INTO volumes (series_id, title, volume_order, epub_title, epub_author, "
        "epub_language, epub_description, epub_illustrator, epub_publisher, epub_identifier) "
        "VALUES (:s, :t, :o, :e, '', 'en', '', '', '', '') RETURNING id"
    ), {"s": series_id, "t": title, "o": order, "e": epub_title}).scalar_one()


def _rows(db, ids):
    return [tuple(db.execute(text(
        "SELECT kind, volume_index, subtitle, volume_order, epub_title, wp_volume_title "
        "FROM volumes WHERE id = :i"), {"i": i}).one()) for i in ids]


def test_titles_split_with_clash_fallback_and_published_names_frozen(
    db, make_user, make_series
):
    user = make_user()
    series = make_series(user, "Mushoku")
    _legacy(db)
    titles = ["Volume 1", "Vol. 2.5 - Extra Bits", "第3巻", "Vol 3", "Prologue"]
    ids = [_insert(db, series.id, t, n, "Keep" if n == 1 else "")
           for n, t in enumerate(titles, start=1)]
    db.add(Document(user_id=user.id, series_id=series.id, volume_id=ids[1], title="c",
                    wp_post_url="https://x/p"))
    db.add(Document(user_id=user.id, series_id=series.id, volume_id=ids[2], title="d"))
    db.flush()

    mig = _migration()
    conn = db.connection()
    mig._split_titles(conn)
    mig._freeze_wp_names(conn)

    rows = _rows(db, ids)
    assert [(k, i, s) for k, i, s, *_ in rows] == [
        ("Volume", Decimal(1), ""),
        ("Volume", Decimal("2.5"), "Extra Bits"),
        ("Volume", Decimal(3), ""),
        ("", None, "Vol 3"),
        ("", None, "Prologue"),
    ]
    assert [r[3] for r in rows] == [1, 2, 3, 4, 5]
    assert [r[4] for r in rows] == ["Keep", "", "", "", ""]
    assert [r[5] for r in rows] == [None, "Vol. 2.5 - Extra Bits", None, None, None]


def test_wp_published_at_alone_freezes_the_name(db, make_user, make_series):
    user = make_user()
    series = make_series(user, "S")
    _legacy(db)
    vid = _insert(db, series.id, "Volume 1", 1)
    db.add(Document(user_id=user.id, series_id=series.id, volume_id=vid, title="c",
                    wp_published_at=datetime(2026, 1, 1, tzinfo=UTC)))
    db.flush()
    _migration()._freeze_wp_names(db.connection())
    assert _rows(db, [vid])[0][5] == "Volume 1"


def test_same_title_in_two_series_parses_independently(db, make_user, make_series):
    user = make_user()
    a, b = make_series(user, "A"), make_series(user, "B")
    _legacy(db)
    va, vb = _insert(db, a.id, "Volume 1", 1), _insert(db, b.id, "Volume 1", 1)
    _migration()._split_titles(db.connection())
    assert [r[:3] for r in _rows(db, [va, vb])] == [("Volume", Decimal(1), "")] * 2


def test_label_titles_dedupes_for_downgrade(db, make_user, make_series):
    """Downgrade fills title from the short label; two labels that collide get ' (n)'."""
    user = make_user()
    series = make_series(user, "S")
    _legacy(db)
    ids = [_insert(db, series.id, t, n) for n, t in enumerate(["x", "y", "z"], start=1)]
    db.execute(text("UPDATE volumes SET kind = 'Volume', volume_index = 1, subtitle = '' "
                    "WHERE id = :i"), {"i": ids[0]})
    db.execute(text("UPDATE volumes SET kind = '', volume_index = NULL, subtitle = 'Volume 1' "
                    "WHERE id = :i"), {"i": ids[1]})
    db.execute(text("UPDATE volumes SET kind = 'Extra', volume_index = NULL, subtitle = 'Q' "
                    "WHERE id = :i"), {"i": ids[2]})
    _migration()._label_titles(db.connection())
    got = [db.execute(text("SELECT title FROM volumes WHERE id = :i"), {"i": i}).scalar_one()
           for i in ids]
    assert got == ["Volume 1", "Volume 1 (2)", "Extra · Q"]


def test_numbers_the_column_cannot_hold_keep_the_whole_title(db, make_user, make_series):
    """>= 10^7 and a 26-digit run (which overflowed quantize()) both fall back."""
    user = make_user()
    series = make_series(user, "S")
    _legacy(db)
    long = "Volume " + "1" * 26
    ids = [_insert(db, series.id, t, n)
           for n, t in enumerate(["Volume 12345678", long], start=1)]
    _migration()._split_titles(db.connection())
    assert [r[:3] for r in _rows(db, ids)] == [("", None, "Volume 12345678"), ("", None, long)]


def test_whitespace_only_differences_are_deduped(db, make_user, make_series):
    user = make_user()
    series = make_series(user, "S")
    _legacy(db)
    ids = [_insert(db, series.id, t, n)
           for n, t in enumerate(["Prologue", " Prologue ", "Vol 1", "Volume 1"], start=1)]
    _migration()._split_titles(db.connection())
    assert [r[:3] for r in _rows(db, ids)] == [
        ("", None, "Prologue"), ("", None, "Prologue (2)"),
        ("Volume", Decimal(1), ""), ("", None, "Volume 1"),
    ]


def test_fallback_title_naming_the_series_keeps_its_epub_title(db, make_user, make_series):
    """The old standalone EPUB import named the volume after the book; the default
    template would render "Book - Book", so the old title becomes the EPUB override."""
    user = make_user()
    series = make_series(user, "Book")
    _legacy(db)
    ids = [_insert(db, series.id, t, n, e) for n, (t, e) in enumerate(
        [("Book", ""), ("book: The Sequel", ""), ("Book Two", "Mine"), ("Afterword", ""),
         ("Book - Volume 2", "")], start=1)]
    _migration()._split_titles(db.connection())
    rows = _rows(db, ids)
    assert [r[4] for r in rows] == ["Book", "book: The Sequel", "Mine", "", ""]
    assert rows[4][:3] == ("Volume", Decimal(2), "")


def test_label_titles_restores_the_published_name(db, make_user, make_series):
    user = make_user()
    series = make_series(user, "S")
    _legacy(db)
    ids = [_insert(db, series.id, t, n) for n, t in enumerate(["x", "y"], start=1)]
    db.execute(text("UPDATE volumes SET kind = 'Volume', volume_index = 2.5, "
                    "subtitle = 'Extra Bits', wp_volume_title = 'Vol. 2.5 - Extra Bits' "
                    "WHERE id = :i"), {"i": ids[0]})
    db.execute(text("UPDATE volumes SET kind = '', volume_index = NULL, "
                    "subtitle = 'Vol. 2.5 - Extra Bits' WHERE id = :i"), {"i": ids[1]})
    _migration()._label_titles(db.connection())
    got = [db.execute(text("SELECT title FROM volumes WHERE id = :i"), {"i": i}).scalar_one()
           for i in ids]
    assert got == ["Vol. 2.5 - Extra Bits", "Vol. 2.5 - Extra Bits (2)"]
