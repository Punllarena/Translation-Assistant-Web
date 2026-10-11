import pytest
from sqlalchemy import select

from api.core.text import load_glossary
from api.models import GlossaryEntry, Profile


@pytest.fixture
def profile(db, me):
    p = Profile(user_id=me.id, name="p", is_default=True)
    db.add(p)
    db.flush()
    return p


def url(profile, tail=""):
    return f"/profiles/{profile.id}/glossary{tail}"


def put(client, profile, *pairs):
    return client.put(
        url(profile), json={"entries": [{"phrase": p, "translation": t} for p, t in pairs]}
    )


def pairs(client, profile):
    return [(e["phrase"], e["translation"]) for e in client.get(url(profile)).json()]


def test_load_glossary_desktop_rules():
    text = "﻿太郎,Taro\r\n\r\n花子\r\na,b,c\n"
    assert load_glossary(text) == [("太郎", "Taro"), ("花子", ""), ("a", "b,c")]


def test_put_replaces_in_order(app_client, profile):
    put(app_client, profile, ("a", "1"), ("b", "2"))
    r = put(app_client, profile, ("b", "2"), ("c", "3"))
    assert r.status_code == 200
    assert [(e["phrase"], e["sort_order"]) for e in r.json()] == [("b", 0), ("c", 1)]
    assert pairs(app_client, profile) == [("b", "2"), ("c", "3")]


def test_put_duplicate_phrase_is_422(app_client, profile):
    assert put(app_client, profile, ("a", "1"), ("a", "2")).status_code == 422


def test_translation_spaces_become_underscores(app_client, profile):
    put(app_client, profile, ("太郎", "Taro Yamada"))
    app_client.post(url(profile), json={"phrase": "花子", "translation": "Hana ko"})
    assert pairs(app_client, profile) == [("太郎", "Taro_Yamada"), ("花子", "Hana_ko")]


def test_post_appends_new_and_updates_existing_in_place(app_client, profile):
    put(app_client, profile, ("a", "1"), ("b", "2"))
    added = app_client.post(url(profile), json={"phrase": "c", "translation": "3"})
    assert added.status_code == 200
    r = app_client.post(url(profile), json={"phrase": "a", "translation": "9"})
    assert (r.json()["phrase"], r.json()["translation"], r.json()["sort_order"]) == ("a", "9", 0)
    assert pairs(app_client, profile) == [("a", "9"), ("b", "2"), ("c", "3")]


def test_empty_phrase_and_nul_are_422(app_client, profile):
    assert app_client.post(url(profile), json={"phrase": "", "translation": "x"}).status_code == 422
    nul = {"phrase": "a\x00", "translation": "x"}
    assert app_client.post(url(profile), json=nul).status_code == 422


def test_import_merges_and_counts(app_client, profile):
    put(app_client, profile, ("a", "1"))
    csv = "﻿a,9\r\nb,2\r\nb,3\r\n,orphan\r\n"
    files = {"file": ("g.csv", csv.encode(), "text/csv")}
    r = app_client.post(url(profile, "/import"), files=files)
    assert r.status_code == 200
    assert r.json() == {"added": 1, "updated": 1, "skipped": 1}
    assert pairs(app_client, profile) == [("a", "9"), ("b", "3")]


def test_import_non_utf8_is_422(app_client, profile):
    shift_jis = "太郎,x".encode("shift_jis")
    files = {"file": ("g.csv", shift_jis, "text/csv")}
    r = app_client.post(url(profile, "/import"), files=files)
    assert r.status_code == 422


def test_import_oversized_is_413(app_client, profile):
    big = b"a,b\n" * (300_000)
    r = app_client.post(url(profile, "/import"), files={"file": ("g.csv", big, "text/csv")})
    assert r.status_code == 413


def test_glossary_applies_to_editor_lines(app_client, profile, me, make_doc):
    doc = make_doc(me, ["太郎が来た"], translated=False)
    app_client.post(url(profile), json={"phrase": "太郎", "translation": "Taro"})
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
def test_another_users_profile_is_404(app_client, db, other_users_profile_id, method, tail, kwargs):
    r = getattr(app_client, method)(f"/profiles/{other_users_profile_id}/glossary{tail}", **kwargs)
    assert r.status_code == 404
    assert db.scalars(select(GlossaryEntry)).all() == []


def test_import_applies_underscore_rule(app_client, profile):
    files = {"file": ("g.csv", b"a,b c\n", "text/csv")}
    assert app_client.post(url(profile, "/import"), files=files).status_code == 200
    assert pairs(app_client, profile) == [("a", "b_c")]


def test_import_skips_nul_and_overlong_rows(app_client, db, profile):
    long_phrase = "p" * 501
    csv = f"ok,1\na\x00b,2\nx,\x00\n{long_phrase},3\n"
    files = {"file": ("g.csv", csv.encode(), "text/csv")}
    r = app_client.post(url(profile, "/import"), files=files)
    assert r.status_code == 200
    assert r.json() == {"added": 1, "updated": 0, "skipped": 3}
    assert pairs(app_client, profile) == [("ok", "1")]


def test_import_over_entry_cap_is_422_and_writes_nothing(app_client, db, profile):
    csv = "".join(f"p{i},t\n" for i in range(10_001))
    files = {"file": ("g.csv", csv.encode(), "text/csv")}
    r = app_client.post(url(profile, "/import"), files=files)
    assert r.status_code == 422
    assert db.scalars(select(GlossaryEntry)).all() == []
