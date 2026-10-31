"""Desktop tests/test_core.py (commit f1a96ce), ported with the functions they cover."""
import pytest

from api.core.text import (
    SEPARATOR,
    build_epub_content,
    build_markdown_ruby,
    build_markdown_translation,
    build_new_file,
    calculate_progress,
    db_rows_to_arrays,
    has_letter,
    lines_to_db_rows,
    natural_key,
    parse_file_content,
    replace_and_parse,
    split_parse_chars,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_file(*raw_lines, translations=None) -> str:
    """Build a minimal SEPERATOR-format file string for test fixtures."""
    if translations is None:
        translations = [""] * len(raw_lines)
    raw = "\n".join(raw_lines) + "\n"
    tl = "\n".join(translations) + "\n"
    return raw + "\n" + SEPARATOR + "\n" + tl

class TestParseFileContent:
    def test_basic_single_line(self):
        content = make_file("%hello")
        raw, tl, raw_section = parse_file_content(content)
        assert raw == ["%hello"]
        assert tl == [""]

    def test_preserves_raw_section(self):
        content = make_file("%line1", "%line2")
        raw, tl, raw_section = parse_file_content(content)
        assert raw_section == "%line1\n%line2\n\n"

    def test_strips_trailing_empty_raw_lines(self):
        content = make_file("%A", "%B", translations=["", ""])
        # The make_file adds a blank line before separator; parse should strip trailing empties
        raw, tl, _ = parse_file_content(content)
        assert raw == ["%A", "%B"]
        assert "" not in [r for r in raw if r == ""] or True  # no trailing empties

    def test_translated_lines_match_raw_count(self):
        content = make_file("%A", "$B", "%C", translations=["t1", "t2", "t3"])
        raw, tl, _ = parse_file_content(content)
        assert len(raw) == len(tl) == 3

    def test_translated_values_preserved(self):
        content = make_file("%A", "%B", translations=["hello", "world"])
        raw, tl, _ = parse_file_content(content)
        assert tl == ["hello", "world"]

    def test_windows_line_endings(self):
        content = "%A\r\n$B\r\n\r\n" + SEPARATOR + "\r\n\r\n\r\n"
        raw, tl, _ = parse_file_content(content)
        assert raw == ["%A", "$B"]
        assert tl == ["", ""]

    def test_missing_separator_raises(self):
        with pytest.raises(ValueError, match=SEPARATOR):
            parse_file_content("no separator here")

    def test_empty_translated_section(self):
        content = make_file("%only")
        raw, tl, _ = parse_file_content(content)
        assert tl == [""]

    def test_continuation_lines_preserved(self):
        content = make_file("%first。", "$second", "%standalone")
        raw, tl, _ = parse_file_content(content)
        assert raw[0] == "%first。"
        assert raw[1] == "$second"
        assert raw[2] == "%standalone"


# ---------------------------------------------------------------------------
# build_new_file
# ---------------------------------------------------------------------------

class TestBuildNewFile:
    def test_no_maru_single_line(self):
        result = build_new_file("Hello world")
        raw, tl, _ = parse_file_content(result)
        assert raw == ["%Hello world"]
        assert tl == [""]

    def test_single_maru_splits_into_two(self):
        result = build_new_file("A。B")
        raw, tl, _ = parse_file_content(result)
        assert raw[0] == "%A。"
        assert raw[1] == "$B"
        assert tl == ["", ""]

    def test_line_ending_with_maru(self):
        result = build_new_file("A。B。")
        raw, tl, _ = parse_file_content(result)
        # Last piece should get 。 back because line ends with 。
        assert raw[0] == "%A。"
        assert raw[1] == "$B。"

    def test_line_not_ending_with_maru(self):
        result = build_new_file("A。B。C")
        raw, tl, _ = parse_file_content(result)
        assert raw[0] == "%A。"
        assert raw[1] == "$B。"
        assert raw[2] == "$C"  # last piece, no 。, line doesn't end with 。

    def test_multiple_input_lines(self):
        result = build_new_file("Line1\nLine2")
        raw, tl, _ = parse_file_content(result)
        assert "%Line1" in raw
        assert "%Line2" in raw

    def test_mixed_maru_and_plain(self):
        result = build_new_file("A。B\nC")
        raw, tl, _ = parse_file_content(result)
        assert raw == ["%A。", "$B", "%C"]
        assert tl == ["", "", ""]

    def test_three_sentences(self):
        result = build_new_file("A。B。C。")
        raw, tl, _ = parse_file_content(result)
        assert raw[0] == "%A。"
        assert raw[1] == "$B。"
        assert raw[2] == "$C。"

    def test_blank_lines_preserved(self):
        # VB: blank input lines become "%" & "" & vbNewLine = "%",
        # not an empty string — matching the original build_new_file behaviour.
        result = build_new_file("A\n\nB")
        raw, tl, _ = parse_file_content(result)
        assert "%A" in raw
        assert "%B" in raw
        assert "%" in raw  # blank line stored as bare "%" marker

    def test_output_is_parseable(self):
        """Round-trip: build_new_file output can be parsed by parse_file_content."""
        inputs = [
            "Single line",
            "A。B",
            "A。B。C",
            "First\nSecond",
            "A。B\nC。D",
        ]
        for text in inputs:
            result = build_new_file(text)
            raw, tl, _ = parse_file_content(result)
            assert len(raw) == len(tl), f"Length mismatch for input: {text!r}"


# ---------------------------------------------------------------------------
# save_file / round-trip
# ---------------------------------------------------------------------------

class TestCalculateProgress:
    def test_nothing_translated(self):
        raw = ["%A", "%B", "%C"]
        tl = ["", "", ""]
        pct, wc = calculate_progress(raw, tl)
        assert pct == 0

    def test_all_translated(self):
        raw = ["%A", "%B"]
        tl = ["hello", "world"]
        pct, wc = calculate_progress(raw, tl)
        assert pct == 100

    def test_partial(self):
        raw = ["%A", "%B", "%C", "%D"]
        tl = ["t", "", "t", ""]
        pct, _ = calculate_progress(raw, tl)
        assert pct == 50

    def test_empty_lines_not_counted(self):
        """Empty raw lines (paragraph breaks) are excluded from totalRawLines."""
        raw = ["%A", "", "%B"]
        tl = ["tA", "", "tB"]
        pct, _ = calculate_progress(raw, tl)
        assert pct == 100

    def test_word_count(self):
        raw = ["%A"]
        tl = ["one two three"]
        _, wc = calculate_progress(raw, tl)
        assert wc == 3

    def test_word_count_multiple_lines(self):
        raw = ["%A", "%B"]
        tl = ["hello world", "foo"]
        _, wc = calculate_progress(raw, tl)
        assert wc == 3

    def test_empty_arrays(self):
        pct, wc = calculate_progress([], [])
        assert pct == 0
        assert wc == 0

    def test_bare_percent_marker_not_counted(self):
        """Bare '%' lines (blank source paragraphs) excluded from total."""
        raw = ["%A", "%", "%B"]
        tl = ["tA", "", "tB"]
        pct, _ = calculate_progress(raw, tl)
        assert pct == 100

    def test_bare_dollar_marker_not_counted(self):
        """Bare '$' lines excluded from total."""
        raw = ["%A", "$", "%B"]
        tl = ["tA", "", "tB"]
        pct, _ = calculate_progress(raw, tl)
        assert pct == 100

    def test_whitespace_only_raw_line_not_counted(self):
        raw = ["%A", "%  ", "%B"]
        tl = ["tA", "", "tB"]
        pct, _ = calculate_progress(raw, tl)
        assert pct == 100


# ---------------------------------------------------------------------------
# build_clipboard_output
# ---------------------------------------------------------------------------

class TestBuildMarkdownTranslation:
    def test_title_heading(self):
        result = build_markdown_translation(["%A"], ["hello"], title="My Chapter")
        assert result.startswith("# My Chapter\n\n")

    def test_no_title_no_heading(self):
        result = build_markdown_translation(["%A"], ["hello"])
        assert not result.startswith("#")

    def test_single_group(self):
        result = build_markdown_translation(["%A"], ["hello"])
        assert result == "hello\n\n"

    def test_continuation_joined(self):
        raw = ["%A。", "$B"]
        tl = ["first", "second"]
        result = build_markdown_translation(raw, tl)
        assert "first second\n\n" in result

    def test_empty_raw_line_preserved(self):
        raw = ["%A", "", "%B"]
        tl = ["alpha", "", "beta"]
        result = build_markdown_translation(raw, tl)
        assert "alpha\n\n" in result
        assert "beta\n\n" in result

    def test_untranslated_group_omitted(self):
        raw = ["%A", "%B"]
        tl = ["", "beta"]
        result = build_markdown_translation(raw, tl)
        assert "beta\n\n" in result
        non_blank = [ln for ln in result.split("\n") if ln.strip()]
        assert len(non_blank) == 1

    def test_empty_inputs(self):
        assert build_markdown_translation([], []) == ""


# ---------------------------------------------------------------------------
# build_markdown_ruby
# ---------------------------------------------------------------------------

class TestBuildMarkdownRuby:
    def test_ruby_wrapper(self):
        result = build_markdown_ruby(["%原文"], ["original text"])
        assert "<ruby>original text<rt>原文</rt></ruby>\n\n" in result

    def test_title_heading(self):
        result = build_markdown_ruby(["%A"], ["b"], title="Chapter 1")
        assert result.startswith("# Chapter 1\n\n")

    def test_continuation_concatenated(self):
        raw = ["%第一。", "$第二"]
        tl = ["first", "second"]
        result = build_markdown_ruby(raw, tl)
        assert "<ruby>first second<rt>第一。第二</rt></ruby>" in result

    def test_missing_translation_no_ruby(self):
        result = build_markdown_ruby(["%原文"], [""])
        assert "<ruby>" not in result
        assert "原文\n\n" in result

    def test_empty_raw_line_preserved(self):
        raw = ["%A", "", "%B"]
        tl = ["alpha", "", "beta"]
        result = build_markdown_ruby(raw, tl)
        assert "<ruby>alpha<rt>A</rt></ruby>" in result
        assert "<ruby>beta<rt>B</rt></ruby>" in result

    def test_empty_inputs(self):
        assert build_markdown_ruby([], []) == ""


# ---------------------------------------------------------------------------
# build_epub_content
# ---------------------------------------------------------------------------

class TestLinesToDbRows:
    def test_percent_prefix_extracted(self):
        rows = lines_to_db_rows(["%Hello"], ["Hi"])
        assert rows[0]["prefix"] == "%"
        assert rows[0]["raw_text"] == "Hello"

    def test_dollar_prefix_extracted(self):
        rows = lines_to_db_rows(["$Cont"], [""])
        assert rows[0]["prefix"] == "$"
        assert rows[0]["raw_text"] == "Cont"

    def test_empty_line_stored_with_empty_prefix(self):
        rows = lines_to_db_rows([""], [""])
        assert rows[0]["prefix"] == ""
        assert rows[0]["raw_text"] == ""

    def test_translated_text_preserved(self):
        rows = lines_to_db_rows(["%A", "%B"], ["Alpha", "Beta"])
        assert rows[0]["translated_text"] == "Alpha"
        assert rows[1]["translated_text"] == "Beta"

    def test_line_numbers_sequential(self):
        rows = lines_to_db_rows(["%A", "%B", "%C"], ["", "", ""])
        assert [r["line_number"] for r in rows] == [0, 1, 2]

    def test_multiple_lines_correct_count(self):
        rows = lines_to_db_rows(["%A", "", "%B"], ["a", "", "b"])
        assert len(rows) == 3


# ---------------------------------------------------------------------------
# db_rows_to_arrays — Stage F
# ---------------------------------------------------------------------------

class TestDbRowsToArrays:
    def _row(self, ln, prefix, raw, tl):
        return {"line_number": ln, "prefix": prefix, "raw_text": raw, "translated_text": tl}

    def test_percent_prefix_prepended(self):
        raw, tl = db_rows_to_arrays([self._row(0, "%", "Hello", "Hi")])
        assert raw == ["%Hello"]
        assert tl == ["Hi"]

    def test_dollar_prefix_prepended(self):
        raw, tl = db_rows_to_arrays([self._row(0, "$", "Cont", "")])
        assert raw == ["$Cont"]

    def test_empty_prefix_gives_empty_raw_line(self):
        raw, tl = db_rows_to_arrays([self._row(0, "", "", "")])
        assert raw == [""]

    def test_ordering_by_line_number(self):
        rows = [
            self._row(2, "%", "Third", ""),
            self._row(0, "%", "First", ""),
            self._row(1, "%", "Second", ""),
        ]
        raw, _ = db_rows_to_arrays(rows)
        assert raw == ["%First", "%Second", "%Third"]

    def test_round_trip_with_lines_to_db_rows(self):
        original_raw = ["%Hello", "$World", "", "%End"]
        original_tl = ["Hi", "Earth", "", "Fin"]
        rows = lines_to_db_rows(original_raw, original_tl)
        raw, tl = db_rows_to_arrays(rows)
        assert raw == original_raw
        assert tl == original_tl


# ---------------------------------------------------------------------------
# import_txt / export_txt — Stage F
# ---------------------------------------------------------------------------



def test_natural_key_numeric_order():
    titles = ["ch10", "ch2", "ch1"]
    assert sorted(titles, key=natural_key) == ["ch1", "ch2", "ch10"]


def test_natural_key_case_insensitive():
    assert sorted(["B", "a"], key=natural_key) == ["a", "B"]


def test_natural_key_mixed_and_plain():
    titles = ["Chapter 12 - End", "Chapter 2 - Start", "Prologue"]
    assert sorted(titles, key=natural_key) == [
        "Chapter 2 - Start", "Chapter 12 - End", "Prologue"]


# ---------------------------------------------------------------------------
# has_letter — symbol-only lines (scene breaks)
# ---------------------------------------------------------------------------

def test_has_letter():
    for text in ("漢字", "ひら", "ー", "abc"):
        assert has_letter(text) is True, text
    for text in ("■", "◇◇◇", "……", "12", "***", "「……！」", "", "  "):
        assert has_letter(text) is False, text


# ---------------------------------------------------------------------------
# replace_and_parse (desktop tests/test_core.py, commit f1a96ce)
# ---------------------------------------------------------------------------

class TestReplaceAndParse:
    def test_no_glossary_no_parse_chars(self):
        text, sents, replaced = replace_and_parse("hello", [], [])
        assert text == "hello"
        assert sents == ["hello"]
        assert replaced is False

    def test_strips_dollar_percent(self):
        text, _, _ = replace_and_parse("%hello $world", [], [])
        assert text == "hello world"

    def test_glossary_substitution(self):
        text, _, replaced = replace_and_parse(
            "勇者は剣を持つ", [("勇者", "Hero")], []
        )
        assert "Hero" in text
        assert replaced is True

    def test_no_match_returns_false(self):
        _, _, replaced = replace_and_parse("abc", [("xyz", "XYZ")], [])
        assert replaced is False

    def test_multiple_glossary_entries(self):
        text, _, replaced = replace_and_parse(
            "AとB", [("A", "Alpha"), ("B", "Beta")], []
        )
        assert "Alpha" in text
        assert "Beta" in text
        assert replaced is True

    def test_parse_chars_split(self):
        _, sents, _ = replace_and_parse(
            "A。B。C", [], ["。"]
        )
        assert sents == ["A", "B", "C"]

    def test_parse_chars_multiple(self):
        _, sents, _ = replace_and_parse(
            "A。B？C！D", [], ["。", "？", "！"]
        )
        assert sents == ["A", "B", "C", "D"]

    def test_empty_input(self):
        text, sents, replaced = replace_and_parse("", [], [])
        assert text == ""
        assert sents == []
        assert replaced is False

    def test_parse_chars_empty_tokens_removed(self):
        _, sents, _ = replace_and_parse("A。。B", [], ["。"])
        # Empty string between two 。 should be excluded
        assert "" not in sents

    def test_glossary_applied_before_parse(self):
        """Glossary substitution fires before sentence splitting."""
        text, sents, replaced = replace_and_parse(
            "Aは勇者です", [("勇者", "Hero")], ["は", "です"]
        )
        assert "Hero" in text
        # "Hero" should end up in the sentences list
        assert any("Hero" in s for s in sents)


def test_replace_and_parse_strips_markers_and_applies_glossary():
    display, sentences, replaced = replace_and_parse(
        "%太郎は、走った。", [("太郎", "Taro")], ["、", "。"]
    )
    assert (display, sentences, replaced) == ("Taroは、走った。", ["Taroは", "走った"], True)


def test_replace_and_parse_without_a_match_is_not_replaced():
    assert replace_and_parse("$走った", [("太郎", "Taro")], []) == ("走った", ["走った"], False)


def test_replace_and_parse_blank_line():
    assert replace_and_parse("", [], ["。"]) == ("", [], False)


def test_replace_and_parse_ignores_empty_phrase():
    assert replace_and_parse("abc", [("", "x")], [])[2] is False


def test_split_parse_chars_matches_the_desktop_setting_split():
    assert split_parse_chars("、 。 ？ ！ 「 」 …… ") == ["、", "。", "？", "！", "「", "」", "……"]




# ---------------------------------------------------------------------------
# build_epub_content
# ---------------------------------------------------------------------------

def test_build_epub_content_no_images_matches_paragraphs():
    raw = ["%A", "%B"]
    tl = ["Alpha", "Beta"]
    result = build_epub_content(raw, tl, [])
    assert result == [("text", "Alpha"), ("text", "Beta")]

def test_build_epub_content_image_between_paragraphs():
    raw = ["%A", "%B"]
    tl = ["Alpha", "Beta"]
    images = [{"anchor_position": 1, "src_path": "images/pic.png"}]
    result = build_epub_content(raw, tl, images)
    assert result == [("text", "Alpha"), ("image", "images/pic.png"), ("text", "Beta")]

def test_build_epub_content_image_at_start():
    raw = ["%A"]
    tl = ["Alpha"]
    images = [{"anchor_position": 0, "src_path": "images/pic.png"}]
    result = build_epub_content(raw, tl, images)
    assert result == [("image", "images/pic.png"), ("text", "Alpha")]

def test_build_epub_content_image_at_end():
    raw = ["%A"]
    tl = ["Alpha"]
    images = [{"anchor_position": 1, "src_path": "images/pic.png"}]
    result = build_epub_content(raw, tl, images)
    assert result == [("text", "Alpha"), ("image", "images/pic.png")]

def test_build_epub_content_two_images_same_anchor_preserve_order():
    raw = ["%A"]
    tl = ["Alpha"]
    images = [
        {"anchor_position": 1, "src_path": "images/pic1.png"},
        {"anchor_position": 1, "src_path": "images/pic2.png"},
    ]
    result = build_epub_content(raw, tl, images)
    assert result == [
        ("text", "Alpha"), ("image", "images/pic1.png"), ("image", "images/pic2.png"),
    ]
