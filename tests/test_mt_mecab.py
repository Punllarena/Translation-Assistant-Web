from pathlib import Path

import pytest

from api.core import nouns
from api.mt import lookup, mecab
from api.mt.base import NeedsSetup


def test_real_mecab_gives_surface_reading_lemma_pos(monkeypatch):
    pytest.importorskip("fugashi")
    monkeypatch.setattr(lookup, "edict_path", lambda: "")
    entries = mecab.run("猫が行った")
    assert [e["surface"] for e in entries][:2] == ["猫", "が"]
    cat = entries[0]
    assert cat["reading"] == "ネコ" and cat["pos"] == "名詞" and cat["matched"] is True
    # MeCab reads 猫が行った as 行う (おこなう); with 学校に it picks 行く.
    went = next(e for e in mecab.run("学校に行った") if e["surface"] == "行っ")
    assert went["lemma"] == "行く"


def test_glosses_come_from_edict_when_configured(monkeypatch):
    pytest.importorskip("fugashi")
    sample = Path(__file__).parent / "fixtures" / "mt" / "edict2_sample"
    monkeypatch.setattr(lookup, "edict_path", lambda: str(sample))
    assert mecab.run("猫")[0]["gloss"] == "cat"


def test_unavailable_mecab_needs_setup(monkeypatch):
    def unavailable():
        raise nouns.Unavailable("MeCab or its dictionary is unavailable on the server.")

    monkeypatch.setattr(nouns, "tagger", unavailable)
    with pytest.raises(NeedsSetup, match="MeCab"):
        mecab.run("猫")
