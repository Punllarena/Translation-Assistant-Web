from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from api.models import Line


def rows(db, doc):
    db.expire_all()
    return [
        (line.prefix, line.raw_text, line.translated_text)
        for line in db.scalars(
            select(Line).where(Line.document_id == doc.id).order_by(Line.line_number)
        )
    ]


def put(client, doc, text, **body):
    return client.put(f"/documents/{doc.id}/source", json={"text": text, **body})


def test_edit_keeps_translations_and_history_by_position(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", "二。"])
    stamp = datetime(2026, 1, 2, tzinfo=UTC)
    for line in db.scalars(select(Line).where(Line.document_id == doc.id)):
        line.translated_at = stamp
    db.flush()
    r = put(app_client, doc, "壱。\n$弐。")
    assert r.status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。"), ("$", "弐。", "tr:二。")]
    assert {line.translated_at for line in db.scalars(select(Line))} == {stamp}


def test_lines_are_not_resplit(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。"])
    assert put(app_client, doc, "壱。弐。").status_code == 200
    assert rows(db, doc) == [("%", "壱。弐。", "tr:一。")]


def test_line_count_change_needs_force(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", "二。"])
    r = put(app_client, doc, "壱。")
    assert r.status_code == 409
    assert "from 2 to 1" in r.json()["detail"]
    assert rows(db, doc) == [("%", "一。", "tr:一。"), ("%", "二。", "tr:二。")]


def test_force_applies_a_shorter_and_a_longer_source(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", "二。"])
    assert put(app_client, doc, "壱。", force=True).status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。")]
    assert put(app_client, doc, "壱。\n\n参。", force=True).status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。"), ("%", "", ""), ("%", "参。", "")]


@pytest.mark.parametrize("text", ["", "   \n  "])
def test_empty_source_is_422(app_client, me, make_doc, text):
    doc = make_doc(me, ["一。"])
    assert put(app_client, doc, text, force=True).status_code == 422


def test_line_cap(app_client, me, make_doc, monkeypatch):
    from api import library

    monkeypatch.setattr(library, "MAX_LINES", 2)
    doc = make_doc(me, ["一。", "二。"])
    r = put(app_client, doc, "a\nb\nc", force=True)
    assert (r.status_code, r.json()["detail"]) == (422, "too many lines (max 2)")


def test_another_users_document_is_404(app_client, me, make_user, make_doc):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    assert put(app_client, theirs, "y").status_code == 404


def test_trailing_blank_line_round_trips_without_409(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", ""])
    assert put(app_client, doc, "壱。\n").status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。"), ("%", "", "tr:")]


def test_space_and_unicode_separators_do_not_split(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。"])
    assert put(app_client, doc, "a b c\x85d\ve").status_code == 200
    assert rows(db, doc) == [("%", "a b c\x85d\ve", "tr:一。")]


def test_crlf_is_a_single_line_break(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。", "二。"])
    assert put(app_client, doc, "壱。\r\n弐。").status_code == 200
    assert rows(db, doc) == [("%", "壱。", "tr:一。"), ("%", "弐。", "tr:二。")]


def test_nul_in_source_is_422_and_changes_nothing(app_client, db, me, make_doc):
    doc = make_doc(me, ["一。"])
    assert put(app_client, doc, "a\x00b", force=True).status_code == 422
    assert rows(db, doc) == [("%", "一。", "tr:一。")]


def test_empty_chapter_takes_its_first_source_without_force(app_client, db, me, make_doc):
    doc = make_doc(me, [])
    assert put(app_client, doc, "壱。\n弐。").status_code == 200
    assert rows(db, doc) == [("%", "壱。", ""), ("%", "弐。", "")]
