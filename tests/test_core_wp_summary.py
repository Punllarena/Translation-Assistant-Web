from api.core.wp import build_chapter_body
from api.core.wp_summary import lines_to_summary, summary_lines


def test_paragraphs_split_on_blank_lines_and_crlf():
    assert summary_lines("One\r\ntwo\r\n\r\n\r\n  Three  \n\n \n") == [
        {"prefix": "%", "translated_text": "One two"},
        {"prefix": "%", "translated_text": "Three"},
    ]


def test_blank_text_has_no_lines():
    assert summary_lines(" \n\n ") == []


def test_body_is_one_p_per_paragraph():
    assert build_chapter_body(summary_lines("A\n\nB")) == "<p>A</p>\n<p>B</p>"


def test_lines_to_summary_groups_continuations_like_the_body():
    lines = [
        {"prefix": "%", "translated_text": "A"},
        {"prefix": "$", "translated_text": "a2"},
        {"prefix": "%", "translated_text": "  "},
        {"prefix": "%", "translated_text": "B"},
    ]
    assert lines_to_summary(lines) == "A a2\n\nB"


def test_round_trip():
    text = "First para.\n\nSecond para."
    assert lines_to_summary(summary_lines(text)) == text
