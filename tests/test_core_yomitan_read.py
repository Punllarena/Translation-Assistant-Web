import zipfile

import pytest

from api.core import yomitan_read
from api.core.yomitan_read import YomitanError, identity_key, read
from tests.fixtures.yomitan import JMDICT_INDEX, JMDICT_ROWS, JMDICT_TAGS, make_zip

SHINWAEI_INDEX = {"title": "新和英", "format": 3, "revision": "Shinwaei1", "sequenced": True}
PLAIN_INDEX = {"title": "T", "format": 3, "revision": "1"}


def _row(expr, reading, tags="", rules="", score=0, gloss=None, seq=0, term_tags=""):
    text = gloss if gloss is not None else f"meaning of {expr}"
    return [expr, reading, tags, rules, score, [text], seq, term_tags]


def test_jmdict_rows_group_by_sequence_and_skip_forms(tmp_path):
    p = make_zip(tmp_path / "j.zip", JMDICT_INDEX,
                 {"term_bank_1.json": JMDICT_ROWS, "tag_bank_1.json": JMDICT_TAGS})
    d = read(str(p))
    e = d.terms["食べる"]
    assert d.terms["たべる"] is e
    assert (e.reading, e.pos, e.gloss) == ("たべる", frozenset({"v1", "vt"}),
                                          "to eat; to live on (e.g. a salary)")
    assert d.meta.identity_key == \
        "url:https://github.com/yomidevs/jmdict-yomitan/releases/latest/download/JMdict_english.json"
    assert d.terms["ヾ"].gloss == "voiced repetition mark in katakana"
    assert "〃" not in d.terms and "おなじ" not in d.terms
    assert d.entry_count == 2 and d.skipped_rows == 0
    assert d.meta.title == "JMdict [2026-10-21]"


def test_shinwaei_shape_no_tags_rules_become_pos_and_untagged_rows_have_empty_pos(tmp_path):
    verb = "走る【はしる】[ローマ字] hashiru\n1 〔人が〕 to run; to dash\n2 〔乗り物が〕 to travel"
    noun = "猫【ねこ】[ローマ字] neko\n1 a cat"
    rows = [
        ["走る", "はしる", "", "v5 v1", 0, [verb], 1, ""],
        ["猫", "ねこ", "", "", 0, [noun], 2, ""],
    ]
    d = read(str(make_zip(tmp_path / "s.zip", SHINWAEI_INDEX, {"term_bank_1.json": rows})))
    assert d.terms["走る"].pos == frozenset({"v5", "v1"})
    assert d.terms["走る"].gloss == "〔人が〕 to run; to dash; 〔乗り物が〕 to travel"
    assert d.terms["猫"].pos == frozenset()
    assert d.terms["猫"].gloss == "a cat"
    assert d.meta.identity_key == "title:新和英"


def test_identity_strips_trailing_bracket():
    assert identity_key({"title": "JMdict [2026-10-21]"}) == "title:JMdict"
    assert identity_key({"title": "A", "indexUrl": ""}) == "title:A"


def test_key_collision_prefers_score_then_popular_then_earlier_sequence(tmp_path):
    index = {**PLAIN_INDEX, "sequenced": True}
    rows = [
        _row("A", "あ", score=10, seq=9), _row("B", "あ", score=50, seq=8),      # score wins
        _row("C", "い", seq=7), _row("D", "い", seq=6, term_tags="P"),           # popular wins
        _row("E", "う", seq=5), _row("F", "う", seq=3), _row("G", "う", seq=4),  # earlier sequence
    ]
    d = read(str(make_zip(tmp_path / "c.zip", index, {"term_bank_1.json": rows})))
    assert d.terms["あ"].headwords == ("B",)
    assert d.terms["い"].headwords == ("D",)
    assert d.terms["う"].headwords == ("F",)
    assert d.terms["A"].headwords == ("A",)  # its own headword key survives


def test_unsequenced_rows_group_by_expression_and_reading(tmp_path):
    rows = [
        _row("猫", "ねこ", score=1, gloss="cat (low)", seq=4),
        _row("猫", "ねこ", score=9, gloss="cat (high)", seq=5),
        _row("猫", "びょう", gloss="other reading", seq=6),
    ]
    d = read(str(make_zip(tmp_path / "u.zip", PLAIN_INDEX, {"term_bank_1.json": rows})))
    assert d.terms["ねこ"].gloss == "cat (high); cat (low)"
    assert d.terms["びょう"].gloss == "other reading"
    assert d.entry_count == 2


def test_empty_reading_defaults_to_first_headword_and_empty_gloss_drops_entry(tmp_path):
    rows = [_row("猫", "", gloss="cat"), _row("犬", "いぬ", gloss="")]
    d = read(str(make_zip(tmp_path / "e.zip", PLAIN_INDEX, {"term_bank_1.json": rows})))
    assert d.terms["猫"].reading == "猫"
    assert "犬" not in d.terms and d.entry_count == 1 and d.skipped_rows == 0


def test_malformed_rows_are_skipped_and_counted(tmp_path):
    rows = [
        [1, 2, 3],
        ["猫", "ねこ", "", "", 0, "notalist", 1, ""],
        _row("犬", "いぬ", gloss="dog"),
    ]
    d = read(str(make_zip(tmp_path / "m.zip", PLAIN_INDEX, {"term_bank_1.json": rows})))
    assert list(d.terms) == ["犬", "いぬ"] and d.skipped_rows == 2


def _case_zip(tmp_path, case):
    p = tmp_path / "z.zip"
    row = [_row("猫", "ねこ")]
    if case == "not_zip":
        p.write_bytes(b"definitely not a zip")
    elif case == "no_index":
        with zipfile.ZipFile(p, "w") as zf:
            zf.writestr("term_bank_1.json", "[]")
    elif case == "format2":
        make_zip(p, {**PLAIN_INDEX, "format": 2}, {"term_bank_1.json": row})
    elif case == "kanji_only":
        make_zip(p, PLAIN_INDEX, {"kanji_bank_1.json": [], "tag_bank_1.json": []})
    elif case == "meta_only":
        make_zip(p, PLAIN_INDEX, {"term_meta_bank_1.json": []})
    elif case == "traversal":
        make_zip(p, PLAIN_INDEX, {"term_bank_1.json": row}, {"../evil.json": b"[]"})
    elif case == "too_big":
        make_zip(p, PLAIN_INDEX, {"term_bank_1.json": row})
    return p


@pytest.mark.parametrize("case,message", [
    ("not_zip", "This is not a zip file"), ("no_index", "has no index.json"),
    ("format2", "Only Yomitan format 3"), ("kanji_only", "has no word definitions"),
    ("meta_only", "has no word definitions"), ("traversal", "unsafe path"),
    ("too_big", "expands to more than"),
])
def test_refusals(tmp_path, monkeypatch, case, message):
    if case == "too_big":
        monkeypatch.setattr(yomitan_read, "MAX_UNPACKED", 10)
    with pytest.raises(YomitanError, match=message):
        read(str(_case_zip(tmp_path, case)))


def test_member_count_bank_size_and_row_limits(tmp_path, monkeypatch):
    p = make_zip(tmp_path / "l.zip", PLAIN_INDEX, {"term_bank_1.json": [_row("猫", "ねこ")]})
    monkeypatch.setattr(yomitan_read, "MAX_MEMBERS", 1)
    with pytest.raises(YomitanError, match="more than 1 files"):
        read(str(p))
    monkeypatch.setattr(yomitan_read, "MAX_MEMBERS", 2000)
    monkeypatch.setattr(yomitan_read, "MAX_BANK", 5)
    with pytest.raises(YomitanError, match="larger than"):
        read(str(p))
    monkeypatch.setattr(yomitan_read, "MAX_BANK", 64 * 1024 * 1024)
    monkeypatch.setattr(yomitan_read, "MAX_ROWS", 0)
    with pytest.raises(YomitanError, match="more than 0 rows"):
        read(str(p))


def test_invalid_json_and_deep_nesting_are_yomitan_errors(tmp_path):
    bad = make_zip(tmp_path / "b.zip", PLAIN_INDEX, {}, {"term_bank_1.json": b"{nope"})
    with pytest.raises(YomitanError, match="term_bank_1.json is not valid JSON"):
        read(str(bad))
    deep = make_zip(tmp_path / "d.zip", PLAIN_INDEX, {},
                    {"term_bank_1.json": ("[" * 100000 + "]" * 100000).encode()})
    with pytest.raises(YomitanError, match="term_bank_1.json is not valid JSON"):
        read(str(deep))
    with zipfile.ZipFile(tmp_path / "i.zip", "w") as zf:
        zf.writestr("index.json", b"{nope")
        zf.writestr("term_bank_1.json", "[]")
    with pytest.raises(YomitanError, match="index.json is not valid JSON"):
        read(str(tmp_path / "i.zip"))


def test_on_bank_reports_each_term_bank(tmp_path):
    banks = {"term_bank_2.json": [_row("犬", "いぬ")], "term_bank_1.json": [_row("猫", "ねこ")]}
    calls = []
    read(str(make_zip(tmp_path / "o.zip", PLAIN_INDEX, banks)), lambda *a: calls.append(a))
    assert calls == [(0, 2, "term_bank_1.json"), (1, 2, "term_bank_2.json")]


def test_on_bank_exception_propagates(tmp_path):
    p = make_zip(tmp_path / "x.zip", PLAIN_INDEX, {"term_bank_1.json": [_row("猫", "ねこ")]})

    def cancel(*_):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        read(str(p), cancel)
