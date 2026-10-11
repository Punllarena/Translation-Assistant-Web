from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from api.models import Document, GlossaryEntry, Line, Profile


@pytest.fixture
def doc(me, make_doc):
    return make_doc(me, ["太郎は、走った。", "", "次"], translated=False)


def _profile(db, user, name="p", *, is_default=False, parse_chars="、 。", glossary=()):
    profile = Profile(user_id=user.id, name=name, is_default=is_default, parse_chars=parse_chars)
    db.add(profile)
    db.flush()
    db.add_all(
        GlossaryEntry(profile_id=profile.id, phrase=p, translation=t, sort_order=i)
        for i, (p, t) in enumerate(glossary)
    )
    db.flush()
    return profile


def _line(db, doc, n):
    db.expire_all()
    return db.scalar(select(Line).where(Line.document_id == doc.id, Line.line_number == n))


def _save(client, doc, *edits):
    body = {"lines": [{"line_number": n, "translated_text": t} for n, t in edits]}
    return client.patch(f"/documents/{doc.id}/lines", json=body)


def test_lines_use_the_default_profile_glossary(app_client, db, me, doc):
    _profile(db, me, is_default=True, glossary=[("太郎", "Taro")])
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["profile"]["name"] == "p"
    first = body["lines"][0]
    assert first["raw_text"] == "太郎は、走った。"
    assert (first["display_text"], first["sentences"], first["replaced"]) == (
        "Taroは、走った。", ["Taroは", "走った"], True
    )
    assert [line["line_number"] for line in body["lines"]] == [0, 1, 2]


def test_series_profile_wins_over_default(app_client, db, me, make_series, make_doc):
    _profile(db, me, "default", is_default=True, glossary=[("次", "Default")])
    series_profile = _profile(db, me, "series", glossary=[("次", "Series")])
    series = make_series(me)
    series.profile_id = series_profile.id
    doc = make_doc(me, ["次"], series=series)
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["lines"][0]["display_text"] == "Series"


def test_profile_id_query_overrides(app_client, db, me, doc):
    _profile(db, me, "default", is_default=True)
    other = _profile(db, me, "other", glossary=[("次", "Next")])
    body = app_client.get(f"/documents/{doc.id}/lines", params={"profile_id": other.id}).json()
    assert (body["profile"]["id"], body["lines"][2]["display_text"]) == (other.id, "Next")


def test_foreign_profile_id_query_is_422(app_client, db, me, make_user, doc):
    theirs = _profile(db, make_user(email="other@example.com"))
    r = app_client.get(f"/documents/{doc.id}/lines", params={"profile_id": theirs.id})
    assert (r.status_code, r.json()["detail"]) == (422, "profile_id: no such item")


def test_no_profile_uses_default_parse_chars(app_client, doc):
    body = app_client.get(f"/documents/{doc.id}/lines").json()
    assert body["profile"] is None
    assert body["lines"][0]["sentences"] == ["太郎は", "走った"]


def test_save_stamps_translated_at_only_from_empty(app_client, db, doc):
    assert _save(app_client, doc, (0, "Taro ran.")).status_code == 204
    first = _line(db, doc, 0).translated_at
    assert first is not None and _line(db, doc, 0).translated_text == "Taro ran."
    assert _save(app_client, doc, (0, "Taro ran off.")).status_code == 204
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


def test_unknown_line_number_is_422_and_writes_nothing(app_client, db, doc):
    r = _save(app_client, doc, (0, "Taro ran."), (99, "ghost"))
    assert (r.status_code, r.json()["detail"]) == (422, "line_number: no such line (99)")
    assert _line(db, doc, 0).translated_text == ""


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
