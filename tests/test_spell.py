import pytest

from api.core import spell
from api.models import CustomWord, Profile


class FakeDict:
    WORDS = {"the", "cat", "sat"}

    def check(self, word):
        return word.lower() in self.WORDS

    def suggest(self, word):
        return ["the", "then", "they", "them", "theme", "there"] if word == "teh" else []


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setattr(spell, "dictionary", lambda: FakeDict())


@pytest.fixture
def profile(db, me):
    p = Profile(user_id=me.id, name="p")
    db.add(p)
    db.flush()
    return p


def check(client, *texts, profile_id=None):
    return client.post("/spell/check", json={"texts": list(texts), "profile_id": profile_id})


def test_misspellings_are_utf16_offsets():
    # 😀 is two UTF-16 code units, 日本 two; "teh" starts at 2 + 1 + 2 + 1 = 6 in JS.
    text = "😀 日本 teh cat"
    assert spell.misspellings(text, set(), FakeDict()) == [(6, 9, "teh")]
    assert text.encode("utf-16-le")[12:18].decode("utf-16-le") == "teh"


def test_check_returns_spans_and_capped_suggestions(app_client, me, fake):
    body = check(app_client, "teh cat", "the cat sat").json()
    assert body["available"] is True
    assert body["results"] == [
        [{"start": 0, "end": 3, "word": "teh",
          "suggestions": ["the", "then", "they", "them", "theme"]}],
        [],
    ]


def test_custom_words_are_not_flagged(app_client, db, me, fake, profile):
    db.add(CustomWord(profile_id=profile.id, word="Taro"))
    db.flush()
    body = check(app_client, "Taro sat", profile_id=profile.id).json()
    assert body["results"] == [[]]


def test_unavailable_dictionary_flags_nothing(app_client, me, monkeypatch):
    monkeypatch.setattr(spell, "dictionary", lambda: None)
    assert check(app_client, "teh").json() == {"available": False, "results": [[]]}


def test_foreign_profile_is_422(app_client, db, me, make_user, fake):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="x")
    db.add(theirs)
    db.flush()
    r = check(app_client, "teh", profile_id=theirs.id)
    assert (r.status_code, r.json()["detail"]) == (422, "profile_id: no such item")


def test_text_count_is_capped(app_client, me, fake):
    assert check(app_client, *(["x"] * 201)).status_code == 422


def test_words_put_is_idempotent_and_case_insensitive(app_client, profile):
    url = f"/profiles/{profile.id}/words"
    assert app_client.put(f"{url}/Taro").status_code == 204
    assert app_client.put(f"{url}/taro").status_code == 204
    assert app_client.get(url).json() == ["Taro"]


def test_words_delete_is_idempotent(app_client, profile):
    url = f"/profiles/{profile.id}/words"
    app_client.put(f"{url}/Taro")
    assert app_client.delete(f"{url}/Taro").status_code == 204
    assert app_client.delete(f"{url}/Taro").status_code == 204
    assert app_client.get(url).json() == []


def test_word_with_whitespace_is_422(app_client, profile):
    assert app_client.put(f"/profiles/{profile.id}/words/two%20words").status_code == 422


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_another_users_profile_words_are_404(app_client, db, me, make_user, method):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="x")
    db.add(theirs)
    db.flush()
    url = f"/profiles/{theirs.id}/words" + ("" if method == "get" else "/Taro")
    assert getattr(app_client, method)(url).status_code == 404


def test_real_enchant_when_installed():
    d = spell.dictionary()
    if d is None:
        pytest.skip("enchant or an English dictionary is not installed")
    assert spell.misspellings("the cat sta", set(), d) == [(8, 11, "sta")]


def test_total_characters_are_capped(app_client, me, fake):
    text = "x" * 90_000  # each under MAX_TEXT_CHARS, together over MAX_TOTAL_CHARS
    assert check(app_client, text, text, text).status_code == 422


def test_misspellings_from_many_threads():
    from concurrent.futures import ThreadPoolExecutor

    d = spell.dictionary() or FakeDict()
    text = "the cat sta"
    with ThreadPoolExecutor(8) as ex:
        results = list(ex.map(lambda _: spell.misspellings(text, set(), d), range(400)))
    assert all(r == results[0] for r in results)
    assert results[0] == [(8, 11, "sta")]
