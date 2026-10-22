import pytest

from api.core import spell
from api.models import CustomWord


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
def series(me, make_series):
    return make_series(me)


def check(client, *texts, series_id=None):
    return client.post("/spell/check", json={"texts": list(texts), "series_id": series_id})


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


def test_series_words_are_not_flagged(app_client, db, me, fake, series):
    db.add(CustomWord(user_id=me.id, series_id=series.id, word="Taro"))
    db.flush()
    body = check(app_client, "Taro sat", series_id=series.id).json()
    assert body["results"] == [[]]


def test_account_word_accepted_everywhere(app_client, db, me, fake, series):
    db.add(CustomWord(user_id=me.id, series_id=None, word="senpai"))
    db.flush()
    assert check(app_client, "senpai sat").json()["results"] == [[]]
    assert check(app_client, "senpai sat", series_id=series.id).json()["results"] == [[]]


def test_series_word_does_not_leak_to_other_series(app_client, db, me, fake, make_series):
    s1, s2 = make_series(me, "S1"), make_series(me, "S2")
    db.add(CustomWord(user_id=me.id, series_id=s1.id, word="Rimuru"))
    db.flush()
    spans = check(app_client, "Rimuru sat", series_id=s2.id).json()["results"][0]
    assert [s["word"] for s in spans] == ["Rimuru"]
    assert [s["word"] for s in check(app_client, "Rimuru").json()["results"][0]] == ["Rimuru"]


def test_another_users_account_words_do_not_apply(app_client, db, me, make_user, fake):
    other = make_user(email="other@example.com")
    db.add(CustomWord(user_id=other.id, series_id=None, word="Rimuru"))
    db.flush()
    assert [s["word"] for s in check(app_client, "Rimuru").json()["results"][0]] == ["Rimuru"]


def test_unavailable_dictionary_flags_nothing(app_client, me, monkeypatch):
    monkeypatch.setattr(spell, "dictionary", lambda: None)
    assert check(app_client, "teh").json() == {"available": False, "results": [[]]}


def test_foreign_series_id_is_422(app_client, me, make_user, make_series, fake):
    theirs = make_series(make_user(email="other@example.com"), "theirs")
    r = check(app_client, "teh", series_id=theirs.id)
    assert (r.status_code, r.json()["detail"]) == (422, "series_id: no such item")


def test_text_count_is_capped(app_client, me, fake):
    assert check(app_client, *(["x"] * 201)).status_code == 422


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


def test_suggestion_lookups_are_capped_per_request(app_client, me, monkeypatch):
    calls = []

    class Counting(FakeDict):
        def suggest(self, word):
            calls.append(word)
            return ["x"]

    monkeypatch.setattr(spell, "dictionary", lambda: Counting())
    words = [f"zq{'a' * (i % 20)}{chr(98 + i // 20)}" for i in range(150)]
    assert len(set(words)) == 150
    body = check(app_client, " ".join(words)).json()
    spans = body["results"][0]
    assert len(spans) == 150
    assert len(calls) == 100
    assert sum(1 for s in spans if s["suggestions"]) == 100


def test_custom_words_match_case_insensitively(app_client, db, me, fake, series):
    db.add(CustomWord(user_id=me.id, series_id=series.id, word="taro"))
    db.flush()
    assert check(app_client, "Taro sat", series_id=series.id).json()["results"] == [[]]
