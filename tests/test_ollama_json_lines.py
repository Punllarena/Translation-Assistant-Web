from api.ollama.json_lines import LineScanner


def test_scanner_emits_each_line_when_closed_even_across_feeds():
    s = LineScanner()
    assert s.feed('{"lines":[{"id":1,"te') == []
    assert s.feed('xt":"a } {"},{"id":2,') == [(1, "a } {")]
    assert s.feed('"text":"b\\"q"}]}') == [(2, 'b"q')]


def test_scanner_skips_objects_missing_a_field():
    s = LineScanner()
    assert s.feed('{"lines":[{"id":1},{"id":2,"text":"x"}]}') == [(2, "x")]
