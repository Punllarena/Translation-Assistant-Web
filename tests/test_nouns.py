import pytest

from api.core import nouns
from api.core.nouns import extract_frequent_nouns
from api.models import GlossaryEntry, Profile


class _FakeTagger:
    """Replays pre-baked MeCab output strings, round-robining through the list."""

    def __init__(self, outputs: list[str]) -> None:
        self._outputs = outputs
        self._idx = 0

    def parse(self, text: str) -> str:
        out = self._outputs[self._idx % len(self._outputs)]
        self._idx += 1
        return out


_OUT_TARO = "太郎\tタロウ\tタロウ\t太郎\t名詞-固有名詞-人名-名\t\t\t1\nEOS\n"
_OUT_BOTH = (
    "太郎\tタロウ\tタロウ\t太郎\t名詞-固有名詞-人名-名\t\t\t1\n"
    "花子\tハナコ\tハナコ\t花子\t名詞-固有名詞-人名-名\t\t\t1\n"
    "EOS\n"
)
_OUT_NUMBER = "100\t100\t100\t100\t名詞-数詞\t\t\t0\nEOS\n"
_OUT_SINGLE = "私\tワタシ\tワタシ\t私\t名詞-代名詞\t\t\t1\nEOS\n"
_OUT_VERB = "走る\tハシル\tハシル\t走る\t動詞-一般\t\t\t1\nEOS\n"


def test_extract_returns_noun_with_count():
    tagger = _FakeTagger([_OUT_TARO, _OUT_TARO])
    result = extract_frequent_nouns(["太郎", "太郎"], set(), min_freq=2, _tagger=tagger)
    assert result == [("太郎", 2)]


def test_extract_skips_verb():
    tagger = _FakeTagger([_OUT_VERB, _OUT_VERB])
    assert extract_frequent_nouns(["走る", "走る"], set(), min_freq=1, _tagger=tagger) == []


def test_extract_skips_number_noun():
    tagger = _FakeTagger([_OUT_NUMBER, _OUT_NUMBER])
    assert extract_frequent_nouns(["100", "100"], set(), min_freq=1, _tagger=tagger) == []


def test_extract_skips_single_char_noun():
    tagger = _FakeTagger([_OUT_SINGLE, _OUT_SINGLE])
    assert extract_frequent_nouns(["私", "私"], set(), min_freq=1, _tagger=tagger) == []


def test_extract_filters_glossary_terms():
    tagger = _FakeTagger([_OUT_TARO, _OUT_TARO])
    assert extract_frequent_nouns(["太郎", "太郎"], {"太郎"}, min_freq=1, _tagger=tagger) == []


def test_extract_sorted_by_count_descending():
    tagger = _FakeTagger([_OUT_BOTH, _OUT_TARO])
    result = extract_frequent_nouns(["太郎花子", "太郎"], set(), min_freq=1, _tagger=tagger)
    assert result[0] == ("太郎", 2)
    assert ("花子", 1) in result


def test_extract_min_freq_filters_low_count():
    tagger = _FakeTagger([_OUT_BOTH])
    assert extract_frequent_nouns(["太郎花子"], set(), min_freq=2, _tagger=tagger) == []


def test_extract_skips_blank_lines():
    tagger = _FakeTagger(["EOS\n"])
    assert extract_frequent_nouns(["", "  "], set(), min_freq=1, _tagger=tagger) == []


def test_real_mecab_finds_a_repeated_name():
    pytest.importorskip("fugashi")
    nouns._tagger.cache_clear()
    terms = dict(nouns.frequent_nouns(["東京に行った。", "東京は広い。"], set(), 2))
    assert terms.get("東京") == 2


@pytest.fixture
def series_with_text(me, make_series, make_doc):
    s = make_series(me)
    make_doc(me, ["太郎", "", "太郎"], series=s)
    return s


def suggest(client, series, **body):
    return client.post(f"/series/{series.id}/phrase-suggestions", json=body)


def test_endpoint_excludes_the_profiles_glossary(
    app_client, db, me, series_with_text, monkeypatch
):
    monkeypatch.setattr(nouns, "tagger", lambda: _FakeTagger([_OUT_BOTH]))
    p = Profile(user_id=me.id, name="p")
    db.add(p)
    db.flush()
    db.add(GlossaryEntry(profile_id=p.id, phrase="花子", translation="Hanako"))
    db.flush()
    body = suggest(app_client, series_with_text, profile_id=p.id, min_freq=2).json()
    assert body == {"available": True, "message": None, "terms": [{"term": "太郎", "count": 2}]}


def test_endpoint_reports_missing_mecab(app_client, series_with_text, monkeypatch):
    def unavailable():
        raise nouns.Unavailable("MeCab is not installed")

    monkeypatch.setattr(nouns, "tagger", unavailable)
    body = suggest(app_client, series_with_text).json()
    assert body["available"] is False and "MeCab" in body["message"] and body["terms"] == []


def test_another_users_series_or_profile_is_404(
    app_client, db, me, make_user, make_series, series_with_text
):
    other = make_user(email="other@example.com")
    theirs = make_series(other, title="theirs")
    their_profile = Profile(user_id=other.id, name="x")
    db.add(their_profile)
    db.flush()
    assert suggest(app_client, theirs).status_code == 404
    r = suggest(app_client, series_with_text, profile_id=their_profile.id)
    assert (r.status_code, r.json()["detail"]) == (422, "profile_id: no such item")


def test_missing_mecab_message_is_static_and_leaks_nothing(
    app_client, series_with_text, monkeypatch
):
    def broken():
        raise RuntimeError("no dictionary at /srv/secret/path")

    monkeypatch.setattr(nouns, "_tagger", broken)
    msg = suggest(app_client, series_with_text).json()["message"]
    assert msg == nouns.SETUP and "/srv" not in msg and ".[mecab]" in msg


def test_suggest_profile_id_is_bounded(app_client, series_with_text):
    assert suggest(app_client, series_with_text, profile_id=2**31).status_code == 422
    assert suggest(app_client, series_with_text, profile_id=0).status_code == 422
