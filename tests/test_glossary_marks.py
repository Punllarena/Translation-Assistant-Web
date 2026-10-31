from api.core.glossary_marks import _walk, glossary_marks
from api.core.text import replace_and_parse


def _tuples(marks):
    return [(m.from_, m.to, m.translation, m.shown_from, m.shown_to) for m in marks]


def test_plain_match_gives_one_mark_with_the_right_offsets():
    marks = glossary_marks("太郎は、走った。", [("太郎", "Taro")])
    assert _tuples(marks) == [(0, 2, "Taro", 0, 4)]


def test_shorter_first_marks_only_the_replaced_text():
    # "太郎は" is listed after "太郎" and never replaces (its text is already gone),
    # so only the shorter phrase becomes a mark.
    marks = glossary_marks("太郎は", [("太郎", "Taro"), ("太郎は", "Taro-wa")])
    assert _tuples(marks) == [(0, 2, "Taro", 0, 4)]


def test_two_phrases_with_one_translation():
    marks = glossary_marks("太郎次", [("太郎", "Taro"), ("次", "Taro")])
    assert _tuples(marks) == [(0, 2, "Taro", 0, 4), (2, 3, "Taro", 4, 8)]


def test_empty_translation_gives_no_mark():
    marks = glossary_marks("太郎は", [("太郎", "")])
    assert marks == []


def test_phrase_inside_an_earlier_output_gives_no_mark_and_does_not_raise():
    # "X" appears only inside the output of "A" -> "AX", so the "X" -> "Y" replacement
    # is not a mark (there is nothing original to put it on); the walk must not raise.
    marks = glossary_marks("A", [("A", "AX"), ("X", "Y")])
    assert len(marks) == 1
    assert (marks[0].from_, marks[0].to, marks[0].translation) == (0, 1, "AX")


def test_astral_char_before_a_match_shifts_offsets_by_two_utf16_units():
    # "𠮷" (U+20BB7) is one code point but two UTF-16 code units, so "走" starts at 2.
    marks = glossary_marks("𠮷走", [("走", "run")])
    assert _tuples(marks) == [(2, 3, "run", 2, 5)]


def test_walk_reconstructs_the_replace_and_parse_output():
    """``_walk`` reproduces ``replace_and_parse``'s replaced text exactly, for every
    glossary above (order, chained replacement, empty translation, astral char)."""
    cases = [
        ("太郎は、走った。", [("太郎", "Taro")]),
        ("太郎は", [("太郎", "Taro"), ("太郎は", "Taro-wa")]),
        ("太郎次", [("太郎", "Taro"), ("次", "Taro")]),
        ("太郎は", [("太郎", "")]),
        ("A", [("A", "AX"), ("X", "Y")]),
        ("𠮷走", [("走", "run")]),
    ]
    for text, glossary in cases:
        _, shown = _walk(text, glossary)
        assert shown == replace_and_parse(text, glossary, [])[0], (text, glossary)


def test_markers_are_stripped_before_matching():
    # $ and % are removed anywhere (as replace_and_parse does), so a phrase split by one
    # still matches the plain text and its mark offset refers to the stripped text.
    marks = glossary_marks("太郎$は", [("太郎は", "Taro-wa")])
    assert _tuples(marks) == [(0, 3, "Taro-wa", 0, 7)]


def test_marks_are_sorted_and_non_overlapping():
    marks = glossary_marks("猫と犬", [("猫", "Cat"), ("犬", "Cat")])
    assert [m.from_ for m in marks] == [0, 2]
    assert all(
        a.to <= b.from_ for a, b in zip(marks, marks[1:], strict=False)
    )
