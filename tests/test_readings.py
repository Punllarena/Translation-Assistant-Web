from types import SimpleNamespace

import pytest

from api.core import nouns, readings
from api.core.readings import Token


def _w(surface, kana, pos1):
    return SimpleNamespace(surface=surface, feature=SimpleNamespace(kana=kana, pos1=pos1))


class _FakeTagger:
    def __init__(self, words) -> None:
        self._words = words

    def __call__(self, text):
        return self._words


_WORDS = [_w("大きく", "オオキク", "形容詞")]


def test_tokens_parse_surface_kana_pos():
    assert readings.tokens("大きく", _FakeTagger(_WORDS)) == [Token("大きく", "オオキク", "形容詞")]


def test_tokens_star_kana_is_empty():
    words = [_w("ABC", "*", "名詞"), _w("、", None, "補助記号")]
    got = readings.tokens("ABC、", _FakeTagger(words))
    assert got == [Token("ABC", "", "名詞"), Token("、", "", "補助記号")]


def test_tokens_keep_every_line():
    words = [_w("今日", "キョウ", "名詞"), _w("\n", None, "空白"), _w("晴れ", "ハレ", "名詞")]
    got = readings.tokens("今日\n晴れ", _FakeTagger(words))
    assert "".join(t.surface for t in got) == "今日\n晴れ"


def test_api_returns_tokens(app_client, me, monkeypatch):
    monkeypatch.setattr(nouns, "tagger", lambda: _FakeTagger(_WORDS))
    r = app_client.post("/readings", json={"text": "大きく"})
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert body["tokens"] == [{"surface": "大きく", "kana": "オオキク", "pos": "形容詞"}]


def test_api_unavailable(app_client, me, monkeypatch):
    def boom():
        raise nouns.Unavailable(nouns.SETUP)

    monkeypatch.setattr(nouns, "tagger", boom)
    r = app_client.post("/readings", json={"text": "大きく"})
    assert r.status_code == 200
    assert r.json() == {"available": False, "message": nouns.SETUP, "tokens": []}


def test_api_text_too_long(app_client, me):
    assert app_client.post("/readings", json={"text": "あ" * 5001}).status_code == 422


def test_api_needs_login(app_client):
    assert app_client.post("/readings", json={"text": "あ"}).status_code == 401


def test_real_mecab_spaces():
    pytest.importorskip("fugashi")
    toks = readings.read("今日は 晴れ")
    assert "".join(t.surface for t in toks if t.surface.strip()) == "今日は晴れ"


def test_real_mecab_newline():
    pytest.importorskip("fugashi")
    toks = readings.read("今日は\n晴れ")
    assert "".join(t.surface for t in toks if t.surface.strip()) == "今日は晴れ"


def test_real_mecab_surface_reading():
    pytest.importorskip("fugashi")
    first = readings.read("大きくなったら")[0]
    assert (first.kana, first.pos) == ("オオキク", "形容詞")
    assert readings.read("行こう")[0].kana == "イコウ"
