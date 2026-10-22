import pytest
from sqlalchemy import select

from api.core.text import load_glossary
from api.models import GlossaryEntry


@pytest.fixture
def series(me, make_series):
    return make_series(me)


def url(series, tail=""):
    return f"/series/{series.id}/glossary{tail}"


def put(client, series, *pairs):
    return client.put(
        url(series), json={"entries": [{"phrase": p, "translation": t} for p, t in pairs]}
    )


def pairs(client, series):
    return [(e["phrase"], e["translation"]) for e in client.get(url(series)).json()]


def test_load_glossary_desktop_rules():
    text = "﻿太郎,Taro\r\n\r\n花子\r\na,b,c\n"
    assert load_glossary(text) == [("太郎", "Taro"), ("花子", ""), ("a", "b,c")]


def test_put_replaces_in_order(app_client, series):
    put(app_client, series, ("a", "1"), ("b", "2"))
    r = put(app_client, series, ("b", "2"), ("c", "3"))
    assert r.status_code == 200
    assert [(e["phrase"], e["sort_order"]) for e in r.json()] == [("b", 0), ("c", 1)]
    assert pairs(app_client, series) == [("b", "2"), ("c", "3")]


def test_put_duplicate_phrase_is_422(app_client, series):
    assert put(app_client, series, ("a", "1"), ("a", "2")).status_code == 422


def test_translation_spaces_become_underscores(app_client, series):
    put(app_client, series, ("太郎", "Taro Yamada"))
    app_client.post(url(series), json={"phrase": "花子", "translation": "Hana ko"})
    assert pairs(app_client, series) == [("太郎", "Taro_Yamada"), ("花子", "Hana_ko")]


def test_post_appends_new_and_updates_existing_in_place(app_client, series):
    put(app_client, series, ("a", "1"), ("b", "2"))
    added = app_client.post(url(series), json={"phrase": "c", "translation": "3"})
    assert added.status_code == 200
    r = app_client.post(url(series), json={"phrase": "a", "translation": "9"})
    assert (r.json()["phrase"], r.json()["translation"], r.json()["sort_order"]) == ("a", "9", 0)
    assert pairs(app_client, series) == [("a", "9"), ("b", "2"), ("c", "3")]


def test_empty_phrase_and_nul_are_422(app_client, series):
    assert app_client.post(url(series), json={"phrase": "", "translation": "x"}).status_code == 422
    nul = {"phrase": "a\x00", "translation": "x"}
    assert app_client.post(url(series), json=nul).status_code == 422


def test_import_merges_and_counts(app_client, series):
    put(app_client, series, ("a", "1"))
    csv = "﻿a,9\r\nb,2\r\nb,3\r\n,orphan\r\n"
    files = {"file": ("g.csv", csv.encode(), "text/csv")}
    r = app_client.post(url(series, "/import"), files=files)
    assert r.status_code == 200
    assert r.json() == {"added": 1, "updated": 1, "skipped": 1}
    assert pairs(app_client, series) == [("a", "9"), ("b", "3")]


def test_import_non_utf8_is_422(app_client, series):
    shift_jis = "太郎,x".encode("shift_jis")
    files = {"file": ("g.csv", shift_jis, "text/csv")}
    r = app_client.post(url(series, "/import"), files=files)
    assert r.status_code == 422


def test_import_oversized_is_413(app_client, series):
    big = b"a,b\n" * (300_000)
    r = app_client.post(url(series, "/import"), files={"file": ("g.csv", big, "text/csv")})
    assert r.status_code == 413


def test_glossary_applies_to_editor_lines(app_client, series, me, make_doc):
    doc = make_doc(me, ["太郎が来た"], series=series, translated=False)
    app_client.post(url(series), json={"phrase": "太郎", "translation": "Taro"})
    lines = app_client.get(f"/documents/{doc.id}/lines").json()["lines"]
    assert lines[0]["display_text"] == "Taroが来た"


@pytest.mark.parametrize(
    ("method", "tail", "kwargs"),
    [
        ("get", "", {}),
        ("put", "", {"json": {"entries": []}}),
        ("post", "", {"json": {"phrase": "a", "translation": "b"}}),
        ("post", "/import", {"files": {"file": ("g.csv", b"a,b", "text/csv")}}),
    ],
)
def test_another_users_series_is_404(app_client, db, other_users_series_id, method, tail, kwargs):
    r = getattr(app_client, method)(f"/series/{other_users_series_id}/glossary{tail}", **kwargs)
    assert r.status_code == 404
    assert db.scalars(select(GlossaryEntry)).all() == []


def test_import_applies_underscore_rule(app_client, series):
    files = {"file": ("g.csv", b"a,b c\n", "text/csv")}
    assert app_client.post(url(series, "/import"), files=files).status_code == 200
    assert pairs(app_client, series) == [("a", "b_c")]


def test_import_skips_nul_and_overlong_rows(app_client, db, series):
    long_phrase = "p" * 501
    csv = f"ok,1\na\x00b,2\nx,\x00\n{long_phrase},3\n"
    files = {"file": ("g.csv", csv.encode(), "text/csv")}
    r = app_client.post(url(series, "/import"), files=files)
    assert r.status_code == 200
    assert r.json() == {"added": 1, "updated": 0, "skipped": 3}
    assert pairs(app_client, series) == [("ok", "1")]


def test_import_over_entry_cap_is_422_and_writes_nothing(app_client, db, series):
    csv = "".join(f"p{i},t\n" for i in range(10_001))
    files = {"file": ("g.csv", csv.encode(), "text/csv")}
    r = app_client.post(url(series, "/import"), files=files)
    assert r.status_code == 422
    assert db.scalars(select(GlossaryEntry)).all() == []
