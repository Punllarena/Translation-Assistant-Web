from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from api.models import Document, GlossaryEntry, Line


@pytest.fixture
def doc(me, make_doc):
    return make_doc(me, ["太郎は、走った。", "", "次"], translated=False)


def _glossary(db, series_id, *pairs):
    db.add_all(
        GlossaryEntry(series_id=series_id, phrase=p, translation=t, sort_order=i)
        for i, (p, t) in enumerate(pairs)
    )
    db.flush()


def _line(db, doc, n):
    db.expire_all()
    return db.scalar(select(Line).where(Line.document_id == doc.id, Line.line_number == n))


def _save(client, doc, *edits):
    body = {"lines": [{"line_number": n, "translated_text": t} for n, t in edits]}
    return client.patch(f"/documents/{doc.id}/lines", json=body)


def test_lines_apply_the_series_glossary(app_client, db, me, doc):
    _glossary(db, doc.series_id, ("太郎", "Taro"))
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert "profile" not in body
    first = body["lines"][0]
    assert first["raw_text"] == "太郎は、走った。"
    assert (first["display_text"], first["sentences"], first["replaced"]) == (
        "Taroは、走った。", ["Taroは", "走った"], True
    )
    assert [line["line_number"] for line in body["lines"]] == [0, 1, 2]


def test_lines_return_glossary_marks(app_client, db, me, doc):
    _glossary(db, doc.series_id, ("太郎", "Taro"))
    first = app_client.get(f"/documents/{doc.id}/lines").json()["lines"][0]
    assert first["plain_text"] == "太郎は、走った。"
    assert [m["from"] for m in first["glossary_marks"]] == [0]
    mark = first["glossary_marks"][0]
    assert (mark["to"], mark["translation"], mark["shown_from"], mark["shown_to"]) == (
        2,
        "Taro",
        0,
        4,
    )


def test_plain_text_strips_markers(app_client, me, make_doc):
    doc = make_doc(me, ["100%です。"], translated=False)
    first = app_client.get(f"/documents/{doc.id}/lines").json()["lines"][0]
    assert first["raw_text"] == "100%です。"
    assert first["plain_text"] == "100です。"


def test_lines_use_own_series_glossary(app_client, db, me, make_series, make_doc):
    a, b = make_series(me, "A"), make_series(me, "B")
    _glossary(db, b.id, ("太郎", "Tarou"))  # inserted first: a leak would apply it
    _glossary(db, a.id, ("太郎", "Taro"))
    doc = make_doc(me, ["太郎"], series=a)
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["lines"][0]["display_text"] == "Taro"


def test_profile_id_query_is_ignored(app_client, db, me, doc):
    r = app_client.get(f"/documents/{doc.id}/lines", params={"profile_id": 999999})
    assert r.status_code == 200


def test_unset_parse_chars_uses_the_default(app_client, doc):
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["lines"][0]["sentences"] == ["太郎は", "走った"]


def test_parse_chars_setting_applies(app_client, doc):
    app_client.put("/settings", json={"parse_chars": "。"})
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["lines"][0]["sentences"] == ["太郎は、走った"]


def test_empty_parse_chars_does_not_split(app_client, doc):
    app_client.put("/settings", json={"parse_chars": ""})
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["lines"][0]["sentences"] == ["太郎は、走った。"]


def test_non_string_parse_chars_falls_back(app_client, doc):
    app_client.put("/settings", json={"parse_chars": 5})
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["lines"][0]["sentences"] == ["太郎は", "走った"]


def test_save_stamps_translated_at_only_from_empty(app_client, db, doc):
    assert _save(app_client, doc, (0, "Taro ran.")).status_code == 200
    first = _line(db, doc, 0).translated_at
    assert first is not None and _line(db, doc, 0).translated_text == "Taro ran."
    assert _save(app_client, doc, (0, "Taro ran off.")).status_code == 200
    assert _line(db, doc, 0).translated_at == first  # an edit keeps the history


def test_clearing_a_translation_clears_translated_at(app_client, db, doc):
    _save(app_client, doc, (0, "Taro ran."))
    _save(app_client, doc, (0, ""))
    assert (_line(db, doc, 0).translated_text, _line(db, doc, 0).translated_at) == ("", None)


def test_save_bumps_document_updated_at(app_client, db, doc):
    doc.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    db.flush()
    _save(app_client, doc, (2, "Next"))
    db.expire_all()
    assert db.get(Document, doc.id).updated_at.year > 2000


def test_only_unknown_lines_leave_updated_at_alone(app_client, db, doc):
    doc.updated_at = datetime(2000, 1, 1, tzinfo=UTC)
    db.flush()
    r = _save(app_client, doc, (99, "gone"))
    assert (r.status_code, r.json()) == (200, {"missing": [99]})
    db.expire_all()
    assert db.get(Document, doc.id).updated_at.year == 2000


def test_unknown_line_numbers_are_reported_and_the_rest_saved(app_client, db, doc):
    r = _save(app_client, doc, (0, "kept"), (99, "gone"))
    assert (r.status_code, r.json()) == (200, {"missing": [99]})
    assert _line(db, doc, 0).translated_text == "kept"


def test_duplicate_line_number_in_batch_is_422(app_client, doc):
    assert _save(app_client, doc, (0, "a"), (0, "b")).status_code == 422


def test_empty_batch_is_422(app_client, doc):
    assert app_client.patch(f"/documents/{doc.id}/lines", json={"lines": []}).status_code == 422


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [("get", {}), ("patch", {"json": {"lines": [{"line_number": 0, "translated_text": "x"}]}})],
)
def test_another_users_lines_are_404(app_client, me, make_user, make_doc, method, kwargs):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    r = getattr(app_client, method)(f"/documents/{theirs.id}/lines", **kwargs)
    assert r.status_code == 404


def test_nul_in_translation_is_422_and_writes_nothing(app_client, db, doc):
    r = _save(app_client, doc, (0, "fine"), (1, "a\x00b"))
    assert r.status_code == 422
    assert "NUL" in r.text
    assert _line(db, doc, 0).translated_text == ""
