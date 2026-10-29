"""COPY CSV: an unquoted empty field is NULL, ``""`` is the empty string (any Python 3.12+)."""

import pytest

from api.backup import copycsv


def test_null_and_empty_string_differ():
    assert copycsv.rows('id,a,b\n1,,""\n') == [["id", "a", "b"], ["1", None, ""]]


def test_quotes_commas_and_newlines_inside_a_field():
    text = 'a,b\n"x, ""y""","line1\r\nline2"\r\n'
    assert copycsv.rows(text) == [["a", "b"], ['x, "y"', "line1\r\nline2"]]


def test_trailing_null_and_no_final_newline():
    assert copycsv.rows("a,b\n1,") == [["a", "b"], ["1", None]]


def test_unterminated_quote_is_refused():
    with pytest.raises(ValueError):
        copycsv.rows('a\n"open\n')
