import pytest
from sqlalchemy import select

from api.models import CustomWord, GlossaryEntry


@pytest.fixture
def series(me, make_series):
    return make_series(me)


def test_account_and_series_lists_are_separate(app_client, series):
    assert app_client.put("/words/senpai").status_code == 204
    assert app_client.put(f"/series/{series.id}/words/Rimuru").status_code == 204
    assert app_client.get("/words").json() == ["senpai"]
    assert app_client.get(f"/series/{series.id}/words").json() == ["Rimuru"]


def test_lists_sort_ignoring_case(app_client, series):
    for word in ("beta", "Alpha", "gamma"):
        app_client.put(f"/words/{word}")
    assert app_client.get("/words").json() == ["Alpha", "beta", "gamma"]


@pytest.mark.parametrize("base", ["/words", "/series/{sid}/words"])
def test_put_is_idempotent_ignoring_case(app_client, series, base):
    url = base.format(sid=series.id)
    assert app_client.put(f"{url}/Rimuru").status_code == 204
    assert app_client.put(f"{url}/rimuru").status_code == 204
    assert app_client.get(url).json() == ["Rimuru"]


@pytest.mark.parametrize("base", ["/words", "/series/{sid}/words"])
def test_delete_is_idempotent(app_client, series, base):
    url = base.format(sid=series.id)
    assert app_client.delete(f"{url}/absent").status_code == 204
    app_client.put(f"{url}/Rimuru")
    assert app_client.delete(f"{url}/RIMURU").status_code == 204
    assert app_client.get(url).json() == []


def test_same_word_may_be_in_both_lists(app_client, series):
    app_client.put("/words/Rimuru")
    app_client.put(f"/series/{series.id}/words/rimuru")
    app_client.delete("/words/Rimuru")
    assert app_client.get(f"/series/{series.id}/words").json() == ["rimuru"]


# A space fails the Word pattern (422). %2F is decoded before routing, so a slash never
# reaches the pattern: the path has an extra segment and matches no route (404).
@pytest.mark.parametrize(("word", "code"), [("a%20b", 422), ("a%2Fb", 404)])
@pytest.mark.parametrize("base", ["/words", "/series/{sid}/words"])
def test_word_with_slash_or_space_is_refused(app_client, db, series, base, word, code):
    url = f"{base.format(sid=series.id)}/{word}"
    assert app_client.put(url).status_code == code
    assert app_client.delete(url).status_code == code
    assert db.scalars(select(CustomWord)).all() == []


def test_word_over_120_chars_is_422(app_client, me):
    assert app_client.put("/words/" + "a" * 121).status_code == 422


def test_users_account_lists_are_separate(app_client, db, me, make_user, login):
    app_client.put("/words/mine")
    make_user(email="other@example.com")
    app_client.post("/auth/logout")
    login(app_client, "other@example.com")
    assert app_client.get("/words").json() == []
    app_client.put("/words/mine")  # not blocked by my row
    assert app_client.get("/words").json() == ["mine"]


def test_deleting_series_cascades_glossary_and_words(app_client, db, me, make_series):
    gone, kept = make_series(me, "Gone"), make_series(me, "Kept")
    for s in (gone, kept):
        app_client.post(f"/series/{s.id}/glossary", json={"phrase": "太郎", "translation": "T"})
        app_client.put(f"/series/{s.id}/words/Rimuru")
    app_client.put("/words/senpai")
    assert app_client.delete(f"/series/{gone.id}").status_code == 204
    db.expire_all()
    glossary = db.scalars(select(GlossaryEntry.series_id)).all()
    words = db.execute(select(CustomWord.series_id, CustomWord.word)).all()
    assert glossary == [kept.id]
    assert sorted(words, key=str) == sorted([(kept.id, "Rimuru"), (None, "senpai")], key=str)
