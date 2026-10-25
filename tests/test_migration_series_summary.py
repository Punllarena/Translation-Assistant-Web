"""The data step of the move-series-summaries revision: a published chapter 0 becomes the
series' ``wp_summary`` and is deleted. Runs inside the test transaction; the db fixture rolls
it all back."""

import importlib.util
from pathlib import Path

from sqlalchemy import text

from api.models import Document, Volume

_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _migration():
    (path,) = _VERSIONS.glob("*_move_series_summaries.py")
    spec = importlib.util.spec_from_file_location("mig_move_series_summaries", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wp(db, doc, index, status):
    doc.wp_chapter_index = index
    doc.wp_status = status
    db.flush()


def _summary(db, series):
    return tuple(db.execute(text(
        "SELECT wp_summary, wp_summary_pending FROM series WHERE id = :s"),
        {"s": series.id}).one())


def _docs(db, series):
    return [tuple(r) for r in db.execute(text(
        "SELECT title, series_order, wp_chapter_index FROM documents WHERE series_id = :s "
        "ORDER BY series_order, id"), {"s": series.id})]


def _run(db):
    logs = _migration().move_summaries(db.connection())
    db.expire_all()
    return logs


def test_live_chapter_zero_becomes_the_summary_and_is_deleted(db, make_user, make_series,
                                                             make_doc):
    user = make_user()
    series = make_series(user)
    ch1 = make_doc(user, ["x"], series=series, order=1, title="Ch1")
    _wp(db, ch1, 1, "publish")
    summary = make_doc(user, ["A", "B"], series=series, order=2, title="Summary")
    _wp(db, summary, 0, "publish")
    db.execute(text("UPDATE series SET wp_summary_pending = true WHERE id = :s"),
               {"s": series.id})
    sid = summary.id

    logs = _run(db)

    assert _summary(db, series) == ("tr:A\n\ntr:B", False)
    assert _docs(db, series) == [("Ch1", 1, 1)]
    assert db.execute(text("SELECT count(*) FROM lines WHERE document_id = :d"),
                      {"d": sid}).scalar_one() == 0
    assert logs == []


def test_continuation_lines_join_into_one_paragraph(db, make_user, make_series, make_doc):
    user = make_user()
    series = make_series(user)
    summary = make_doc(user, ["A", "B", "C"], series=series, order=1)
    _wp(db, summary, 0, "future")
    db.execute(text("UPDATE lines SET prefix = '$' WHERE document_id = :d AND line_number = 1"),
               {"d": summary.id})

    _run(db)

    assert _summary(db, series) == ("tr:A tr:B\n\ntr:C", False)


def test_unsent_chapter_zero_is_kept_with_its_index_cleared(db, make_user, make_series,
                                                           make_doc):
    user = make_user()
    series = make_series(user)
    doc = make_doc(user, ["A"], series=series, order=1, title="Unsent")
    _wp(db, doc, 0, "")
    gone = make_doc(user, ["B"], series=series, order=2, title="Gone")
    _wp(db, gone, 0, "missing")

    _run(db)

    assert _summary(db, series) == ("", False)
    assert _docs(db, series) == [("Unsent", 1, None), ("Gone", 2, None)]


def test_renumbers_and_logs_shifted_live_chapters(db, make_user, make_series, make_doc):
    user = make_user()
    series = make_series(user)
    vol = Volume(series_id=series.id, subtitle="V", volume_order=1)
    db.add(vol)
    db.flush()
    summary = make_doc(user, ["A"], series=series, order=1, title="Summary", volume=vol)
    _wp(db, summary, 0, "publish")
    ch = make_doc(user, ["x"], series=series, order=2, title="Shifted chapter", volume=vol)
    _wp(db, ch, 2, "publish")
    draft = make_doc(user, ["y"], series=series, order=3, title="Draft chapter", volume=vol)
    _wp(db, draft, 9, "draft")

    logs = _run(db)

    assert _docs(db, series) == [("Shifted chapter", 1, 2), ("Draft chapter", 2, 9)]
    assert any("Shifted chapter" in line for line in logs)
    assert not any("Draft chapter" in line for line in logs)


def test_illustrations_do_not_count_toward_the_display_number(db, make_user, make_series,
                                                             make_doc):
    user = make_user()
    series = make_series(user)
    vol = Volume(series_id=series.id, subtitle="V", volume_order=1)
    db.add(vol)
    db.flush()
    ill = make_doc(user, [], series=series, order=1, title="Illustrations", volume=vol)
    ill.is_illustrations = True
    _wp(db, ill, 5, "publish")
    ch = make_doc(user, ["x"], series=series, order=2, title="Chapter one", volume=vol)
    _wp(db, ch, 1, "publish")
    summary = make_doc(user, ["A"], series=series, order=3, title="Summary")
    _wp(db, summary, 0, "publish")

    logs = _run(db)

    assert _docs(db, series) == [("Illustrations", 1, 5), ("Chapter one", 2, 1)]
    assert logs == []


def test_syosetu_series_is_not_renumbered(db, make_user, make_series, make_doc):
    user = make_user()
    series = make_series(user)
    series.syosetu_url = "https://ncode.syosetu.com/n1234ab/"
    summary = make_doc(user, ["A"], series=series, order=0, title="Summary")
    _wp(db, summary, 0, "publish")
    ch = make_doc(user, ["x"], series=series, order=5, title="Ch5")
    _wp(db, ch, 5, "publish")
    ch7 = make_doc(user, ["y"], series=series, order=7, title="Ch7")
    _wp(db, ch7, 6, "publish")

    logs = _run(db)

    assert _summary(db, series) == ("tr:A", False)
    assert _docs(db, series) == [("Ch5", 5, 5), ("Ch7", 7, 6)]
    assert any("Ch7" in line for line in logs)
    assert not any("Ch5" in line for line in logs)


def test_two_live_summaries_use_the_lowest_id_and_delete_both(db, make_user, make_series,
                                                             make_doc):
    user = make_user()
    series = make_series(user, "Twice")
    first = make_doc(user, ["first"], series=series, order=2, title="Summary 1")
    _wp(db, first, 0, "publish")
    second = make_doc(user, ["second"], series=series, order=1, title="Summary 2")
    _wp(db, second, 0, "future")
    ch = make_doc(user, ["x"], series=series, order=3, title="Ch")
    _wp(db, ch, 1, "publish")
    ids = [first.id, second.id]

    logs = _run(db)

    assert _summary(db, series) == ("tr:first", False)
    assert _docs(db, series) == [("Ch", 1, 1)]
    assert any("Twice" in line and "2" in line for line in logs)
    assert db.query(Document).filter(Document.id.in_(ids)).count() == 0


def test_other_series_are_untouched(db, make_user, make_series, make_doc):
    user = make_user()
    affected, other = make_series(user, "Affected"), make_series(user, "Other")
    summary = make_doc(user, ["A"], series=affected, order=1)
    _wp(db, summary, 0, "publish")
    # Gaps and an index mismatch in a series with no chapter 0 stay as they are.
    a = make_doc(user, ["x"], series=other, order=3, title="Other A")
    _wp(db, a, 7, "publish")
    make_doc(user, ["y"], series=other, order=9, title="Other B")
    db.execute(text("UPDATE series SET wp_summary = 'kept', wp_summary_pending = true "
                    "WHERE id = :s"), {"s": other.id})

    logs = _run(db)

    assert _summary(db, other) == ("kept", True)
    assert _docs(db, other) == [("Other A", 3, 7), ("Other B", 9, None)]
    assert not any("Other" in line for line in logs)
