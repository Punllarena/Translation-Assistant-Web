from pathlib import Path

import pytest

from api.mt import jparser
from api.mt.base import NeedsSetup

FX = Path(__file__).parent / "fixtures" / "mt"


@pytest.fixture
def index():
    return jparser.load_index(str(FX / "edict2_sample"))


def test_index_reads_euc_jp_and_cleans_glosses(index):
    assert index["猫"].gloss == "cat" and index["ねこ"].headwords == ("猫",)
    assert index["行く"].pos_tags == {"v5k-s", "vi"}


def test_common_variant_wins_duplicate_headword(index):
    assert index["目"].gloss == "eye"


def test_greedy_longest_match_and_unmatched_characters(index):
    entries = jparser.analyze("猫X。", index, [])
    assert [(e["surface"], e["gloss"], e["matched"]) for e in entries] == [
        ("猫", "cat", True), ("X", "", False)
    ]  # "。" is skipped, as on the desktop


def test_deconjugation_reports_base_form_and_tense(index):
    rules = jparser.load_rules(str(FX / "conjugations_sample.json"))
    [entry] = jparser.analyze("行った", index, rules)
    assert (entry["surface"], entry["base_form"], entry["tense"]) == ("行った", "行く", "Past")


def test_run_without_an_edict_path_needs_setup(monkeypatch):
    monkeypatch.setattr(jparser, "_edict_path", lambda: "")
    with pytest.raises(NeedsSetup, match="EDICT2"):
        jparser.run("猫")
