from api.ollama.chunks import Item, chunk_index, context_before, cut, paragraphs


def mk(n, p="%", t=None):
    return Item(n, p, t if t is not None else f"s{n}")


def test_paragraph_is_percent_head_with_dollar_tails():
    ps = paragraphs([mk(0), mk(1, "$"), mk(2), mk(3, "", ""), mk(4, "$")])
    assert [[i.line_number for i in p] for p in ps] == [[0, 1], [2], [4]]


def test_cut_never_splits_a_paragraph_and_long_paragraph_stands_alone():
    items = [mk(0), mk(1, "$"), mk(2), mk(3), mk(4, "$"), mk(5, "$"), mk(6, "$")]
    assert [[i.line_number for i in c] for c in cut(items, 3)] == [[0, 1, 2], [3, 4, 5, 6]]


def test_cut_zero_is_whole_chapter():
    assert len(cut([mk(n) for n in range(40)], 0)) == 1


def test_chunk_index_and_context_before():
    chunks = cut([mk(n) for n in range(10)], 4)
    assert chunk_index(chunks, 5) == 1 and chunk_index(chunks, 99) is None
    assert [i.line_number for i in context_before([mk(n) for n in range(10)], 4, 2)] == [2, 3]
