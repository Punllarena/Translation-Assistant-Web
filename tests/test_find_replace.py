from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from api.core.text import needle_pattern, replace_all
from api.models import Line


def test_replace_all_is_literal_and_case_aware():
    p = needle_pattern("a.b", case_sensitive=False)
    assert replace_all(p, "A.B axb a.b", r"$1\1\n") == r"$1\1\n axb $1\1\n"
    assert replace_all(needle_pattern("Taro", True), "Taro taro", "X") == "X taro"


@pytest.fixture
def series(me, make_series, make_doc):
    s = make_series(me)
    make_doc(me, ["一", "二"], series=s, order=1, title="Ch2")
    make_doc(me, ["三"], series=s, order=0, title="Ch1")
    return s


def _set(db, doc_title_lines):
    for line in db.scalars(select(Line)):
        key = (line.document.title, line.line_number)
        if key in doc_title_lines:
            line.translated_text = doc_title_lines[key]
    db.flush()


def find(client, series, q, **params):
    return client.get(f"/series/{series.id}/find", params={"q": q, **params})


def test_find_lists_matches_in_series_order_with_preview(app_client, db, series):
    _set(db, {("Ch2", 0): "Taro ran", ("Ch2", 1): "no", ("Ch1", 0): "TARO sat"})
    body = find(app_client, series, "taro", replace="Tarou").json()
    assert body["truncated"] is False
    assert [(m["title"], m["line_number"], m["before"], m["after"]) for m in body["matches"]] == [
        ("Ch1", 0, "TARO sat", "Tarou sat"),
        ("Ch2", 0, "Taro ran", "Tarou ran"),
    ]
    assert find(app_client, series, "taro", case_sensitive=True).json()["matches"] == []


def test_find_treats_like_wildcards_literally(app_client, db, series):
    _set(db, {("Ch1", 0): "100% sure", ("Ch2", 0): "100 sure"})
    titles = [m["title"] for m in find(app_client, series, "0%").json()["matches"]]
    assert titles == ["Ch1"]


def test_find_rejects_nul_and_overlong_needles(app_client, series):
    assert find(app_client, series, "a\x00b").status_code == 422
    assert find(app_client, series, "x" * 1001).status_code == 422
    assert find(app_client, series, "").status_code == 422


def replace(client, series, targets, find="Taro", repl="Tarou", case_sensitive=False):
    return client.post(
        f"/series/{series.id}/replace",
        json={"find": find, "replace": repl, "case_sensitive": case_sensitive, "targets": targets},
    )


def test_replace_applies_reviewed_targets_only(app_client, db, series):
    _set(db, {("Ch1", 0): "Taro sat", ("Ch2", 0): "Taro ran"})
    matches = find(app_client, series, "Taro").json()["matches"]
    chosen = [{k: m[k] for k in ("document_id", "line_number", "before")} for m in matches[:1]]
    assert replace(app_client, series, chosen).json() == {"replaced": 1, "skipped": 0}
    db.expire_all()
    texts = sorted(line.translated_text for line in db.scalars(select(Line)))
    assert texts == ["Taro ran", "Tarou sat", "tr:二"]


def test_replace_skips_lines_changed_since_search(app_client, db, series):
    _set(db, {("Ch1", 0): "Taro sat"})
    m = find(app_client, series, "Taro").json()["matches"][0]
    _set(db, {("Ch1", 0): "Taro stood"})
    target = {k: m[k] for k in ("document_id", "line_number", "before")}
    assert replace(app_client, series, [target]).json() == {"replaced": 0, "skipped": 1}
    db.expire_all()
    assert "Taro stood" in [line.translated_text for line in db.scalars(select(Line))]


def test_replace_to_empty_clears_translated_at(app_client, db, series):
    _set(db, {("Ch1", 0): "Taro"})
    for line in db.scalars(select(Line)):
        line.translated_at = datetime.now(UTC)
    db.flush()
    m = find(app_client, series, "Taro").json()["matches"][0]
    target = {k: m[k] for k in ("document_id", "line_number", "before")}
    assert replace(app_client, series, [target], repl="").json() == {"replaced": 1, "skipped": 0}
    db.expire_all()
    line = db.scalar(select(Line).where(Line.translated_text == ""))
    assert line is not None and line.translated_at is None


def test_replace_ignores_documents_outside_the_series(app_client, db, me, series, make_doc):
    loose = make_doc(me, ["x"], title="loose")
    _set(db, {("loose", 0): "Taro"})
    target = {"document_id": loose.id, "line_number": 0, "before": "Taro"}
    assert replace(app_client, series, [target]).json() == {"replaced": 0, "skipped": 1}


def test_another_users_series_is_404(app_client, me, make_user, make_series):
    theirs = make_series(make_user(email="other@example.com"))
    assert find(app_client, theirs, "a").status_code == 404
    assert replace(app_client, theirs, []).status_code == 404


def test_find_truncates_at_the_cap(app_client, db, series, monkeypatch):
    from api.routers import memory

    monkeypatch.setattr(memory, "MAX_MATCHES", 1)
    _set(db, {("Ch1", 0): "Taro sat", ("Ch2", 0): "Taro ran"})
    body = find(app_client, series, "Taro").json()
    assert body["truncated"] is True
    assert [(m["title"], m["line_number"]) for m in body["matches"]] == [("Ch1", 0)]


def test_replace_with_dollar_sign_is_literal_over_http(app_client, db, series):
    _set(db, {("Ch1", 0): "a.b axb"})
    m = find(app_client, series, "a.b").json()["matches"][0]
    target = {k: m[k] for k in ("document_id", "line_number", "before")}
    assert replace(app_client, series, [target], find="a.b", repl="$1").json() == {
        "replaced": 1,
        "skipped": 0,
    }
    db.expire_all()
    assert "$1 axb" in [line.translated_text for line in db.scalars(select(Line))]
