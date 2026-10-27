import pytest

from api.core import nouns, readings
from api.core.readings import Token


class _FakeTagger:
    def __init__(self, out: str) -> None:
        self._out = out

    def parse(self, text: str) -> str:
        return self._out


_OUT = "大きく\tオーキク\tオオキク\t大きい\t形容詞-一般\nEOS\n"


def test_tokens_parse_surface_kana_pos():
    assert readings.tokens("大きく", _FakeTagger(_OUT)) == [Token("大きく", "オオキク", "形容詞")]


def test_tokens_star_kana_is_empty():
    out = "ABC\tABC\t*\tABC\t名詞-普通名詞\nEOS\n"
    assert readings.tokens("ABC", _FakeTagger(out)) == [Token("ABC", "", "名詞")]


def test_api_returns_tokens(app_client, me, monkeypatch):
    monkeypatch.setattr(nouns, "tagger", lambda: _FakeTagger(_OUT))
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
    assert "".join(t.surface for t in toks) == "今日は晴れ"
