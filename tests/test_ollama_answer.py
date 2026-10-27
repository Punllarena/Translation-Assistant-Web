import pytest

from api.ollama.answer import AnswerError, check, halves
from api.ollama.chunks import Item

ASK = [Item(1, "%", "a"), Item(2, "$", "b"), Item(3, "%", "c")]


def test_valid_answer_and_empty_dollar_line():
    assert check('{"lines":[{"id":1,"text":" A "},{"id":2,"text":""},{"id":3,"text":"C"}]}', ASK) \
        == {1: "A", 2: "", 3: "C"}


@pytest.mark.parametrize("bad", [
    '{"lines":[{"id":1,"text":"A"},{"id":3,"text":"C"}]}',                       # missing
    '{"lines":[{"id":3,"text":"C"},{"id":1,"text":"A"},{"id":2,"text":"B"}]}',   # order
    '{"lines":[{"id":1,"text":"A"},{"id":2,"text":"B"},{"id":3,"text":"C"},{"id":9,"text":"X"}]}',
    '{"lines":[{"id":1,"text":""},{"id":2,"text":"B"},{"id":3,"text":"C"}]}',    # empty % line
    '{"lines":[{"id":1,"text":"A"},{"id":2,"text":5},{"id":3,"text":"C"}]}',
    '[]',
    'not json',
])
def test_bad_answers_raise(bad):
    with pytest.raises(AnswerError):
        check(bad, ASK)


def test_halves_prefers_paragraph_boundary():
    a, b = halves([Item(1, "%", "a"), Item(2, "$", "b"), Item(3, "$", "c"), Item(4, "%", "d")])
    assert [i.line_number for i in a] == [1, 2, 3]
    assert [i.line_number for i in b] == [4]


def test_halves_without_paragraph_boundary_splits_in_the_middle():
    a, b = halves([Item(1, "%", "a"), Item(2, "$", "b"), Item(3, "$", "c"), Item(4, "$", "d")])
    assert len(a) == 2 and len(b) == 2
