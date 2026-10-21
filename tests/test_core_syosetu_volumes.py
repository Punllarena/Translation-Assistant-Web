from api.core.syosetu_volumes import heading_sequence, marker_of, offered_markers, targets

SEQ = [[2, "★ 一日"], [5, "◇ 編A"], [8, "★ 二日"], [9, "◇ 編B"], [12, "※"]]


def test_marker_of():
    assert marker_of("  ★ 一日") == "★" and marker_of("※") == "※"
    assert marker_of("第一章") is None and marker_of("1. a") is None and marker_of("あ") is None
    assert marker_of("") is None and marker_of("   ") is None


def test_heading_sequence_from_index():
    idx = [{"num": 1, "group": None}, {"num": 2, "group": "A"}, {"num": 3, "group": "A"},
           {"num": 4, "group": "B"}]
    assert heading_sequence(idx) == [[2, "A"], [4, "B"]]


def test_offered_markers():
    assert offered_markers(SEQ) == [{"marker": "★", "headings": 2}, {"marker": "◇", "headings": 2}]


def test_offered_markers_keeps_the_saved_one():
    assert offered_markers(SEQ, "◎")[-1] == {"marker": "◎", "headings": 0}
    assert offered_markers(SEQ, "※")[-1] == {"marker": "※", "headings": 1}
    assert offered_markers(SEQ, "★") == offered_markers(SEQ)


def test_targets_all():
    assert targets(SEQ, [1, 2, 6, 12], "all", "") == {1: None, 2: "★ 一日", 6: "◇ 編A", 12: "※"}


def test_targets_marker_uses_earlier_starting_heading_even_if_unfetched():
    assert targets(SEQ, [1, 6, 10, 13], "marker", "★") == {
        1: None, 6: "★ 一日", 10: "★ 二日", 13: "★ 二日"}


def test_targets_off():
    assert set(targets(SEQ, [2, 9], "off", "").values()) == {None}
