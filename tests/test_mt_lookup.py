import json
from pathlib import Path

import pytest

from api import yomitan_store as ys
from api.core import nouns
from api.core.yomitan_read import FlatEntry, Meta, Parsed
from api.mt import jparser, lookup, mecab
from api.mt.base import NeedsSetup
from api.mt.jparser import DictEntry
from api.mt.lookup import Lookup, candidate_keys

FX = Path(__file__).parent / "fixtures" / "mt"


def install(db, key, terms, pos=frozenset()):
    flat = {
        k: FlatEntry((k,), "", frozenset(pos), gloss) for k, gloss in terms.items()
    }
    meta = Meta(f"Dict {key}", "r1", "", "", "", key)
    return ys.token(ys.install(db, Parsed(meta, flat, len(flat), 0)).dictionary.id)


@pytest.fixture
def edict_files(monkeypatch):
    monkeypatch.setattr(lookup, "edict_path", lambda: str(FX / "edict2_sample"))
    monkeypatch.setattr(lookup, "conj_path", lambda: str(FX / "conjugations_sample.json"))


def test_lookup_first_layer_wins_and_all_lists_in_order():
    a = DictEntry(("x",), "", frozenset(), "a")
    b = DictEntry(("x",), "", frozenset(), "b")
    lk = Lookup([{"y": a}, {"x": a}, {"x": b}])
    assert lk["x"] is a and lk.get("x") is a and lk.get("zz") is None
    assert "x" in lk and "zz" not in lk
    assert lk.all("x") == [a, b] and lk.all("zz") == []


def test_candidate_keys_include_substrings_and_deconjugation_bases():
    rules = jparser.load_rules(str(FX / "conjugations_sample.json"))
    keys = candidate_keys("行った 猫", rules)
    assert {"行った", "猫", "行く"} <= keys and " " not in "".join(keys)


def test_order_decides_which_gloss_jparser_shows(db, lookup_session, edict_files, make_user):
    tok = install(db, "A", {"猫": "cat (yomitan)"})
    assert jparser.run("猫")[0]["gloss"] == "cat"
    ys.set_order(db, [tok, "edict"], make_user().id)
    assert jparser.run("猫")[0]["gloss"] == "cat (yomitan)"


def test_deconjugation_through_a_yomitan_v1_entry(
    db, lookup_session, edict_files, monkeypatch, tmp_path
):
    def tense(name, suffix):
        return {"Tense": name, "Suffix": suffix, "Negative": False, "Formal": False}

    rules = [{"Name": "v1", "Part of Speech": "verb",
              "Tenses": [tense("Remove", "る"), tense("Non-past", "る"), tense("Past", "た")]}]
    path = tmp_path / "conj.json"
    path.write_text(json.dumps(rules), encoding="utf-8")
    monkeypatch.setattr(lookup, "conj_path", lambda: str(path))
    install(db, "A", {"食べる": "to eat"}, pos={"v1", "vt"})
    [entry] = jparser.run("食べた")
    assert (entry["base_form"], entry["tense"], entry["gloss"]) == ("食べる", "Past", "to eat")


def test_posless_yomitan_entry_does_not_hide_edict_for_deconjugation(
    db, lookup_session, edict_files, make_user
):
    tok = install(db, "A", {"行く": "yomitan go"})
    ys.set_order(db, [tok, "edict"], make_user().id)
    [entry] = jparser.run("行った")
    assert (entry["base_form"], entry["tense"]) == ("行く", "Past")
    assert entry["gloss"] != "yomitan go"
    assert jparser.run("行く")[0]["gloss"] == "yomitan go"  # direct matches stay first-hit


def test_yomitan_only_without_edict_or_conjugations_works(db, lookup_session, monkeypatch):
    monkeypatch.setattr(lookup, "edict_path", lambda: "")
    monkeypatch.setattr(lookup, "conj_path", lambda: "")
    with pytest.raises(NeedsSetup, match="Yomitan"):
        jparser.run("猫")
    install(db, "A", {"猫": "cat (yomitan)"})
    [entry] = jparser.run("猫")
    assert entry["matched"] is True and entry["gloss"] == "cat (yomitan)"


def test_mecab_gloss_from_a_yomitan_only_word(db, lookup_session, monkeypatch):
    pytest.importorskip("fugashi")
    try:
        nouns.tagger()
    except nouns.Unavailable:
        pytest.skip("MeCab dictionary unavailable")
    monkeypatch.setattr(lookup, "edict_path", lambda: "")
    install(db, "A", {"猫": "cat (yomitan)"})
    assert mecab.run("猫")[0]["gloss"] == "cat (yomitan)"
