from bs4 import BeautifulSoup

from api.core.epub_runs import Piece, plan_chapters, units


def _anch(**kw):
    return {f"{k}.xhtml": v for k, v in kw.items()}


def test_plain_spine_one_chapter_per_file():
    spine = ["a.xhtml", "b.xhtml"]
    toc = [("One", "a.xhtml", None), ("Two", "b.xhtml", None)]
    out = plan_chapters(spine, toc, {})
    assert [(p.title, p.key) for p in out] == [("One", "a.xhtml"), ("Two", "b.xhtml")]
    assert out[1].pieces == (Piece("b.xhtml", None, None),)


def test_fragment_mid_file_cuts_there():
    toc = [("One", "a.xhtml", "t1"), ("Two", "a.xhtml", "t2")]
    out = plan_chapters(["a.xhtml"], toc, _anch(a=["t1", "t2"]))
    assert [p.title for p in out] == ["a", "One", "Two"]  # text before t1 is its own chapter
    assert out[1].pieces == (Piece("a.xhtml", "t1", "t2"),)
    assert out[2].pieces == (Piece("a.xhtml", "t2", None),)
    assert out[2].key == "a.xhtml#t2"


def test_chapter_crosses_files():
    spine = ["a.xhtml", "b.xhtml", "c.xhtml"]
    toc = [("One", "a.xhtml", "t1"), ("Two", "c.xhtml", "t2")]
    out = plan_chapters(spine, toc, _anch(a=["t1"], c=["t2"]))
    one = next(p for p in out if p.title == "One")
    assert one.pieces == (
        Piece("a.xhtml", "t1", None), Piece("b.xhtml", None, None), Piece("c.xhtml", None, "t2"),
    )
    two = next(p for p in out if p.title == "Two")
    assert two.pieces == (Piece("c.xhtml", "t2", None),)


def test_five_chapters_in_one_file():
    ids = [f"t{i}" for i in range(5)]
    toc = [(f"C{i}", "a.xhtml", t) for i, t in enumerate(ids)]
    out = plan_chapters(["a.xhtml"], toc, _anch(a=ids))
    chapters = out[1:]
    assert [p.title for p in chapters] == [f"C{i}" for i in range(5)]
    assert chapters[2].pieces == (Piece("a.xhtml", "t2", "t3"),)
    assert chapters[4].pieces == (Piece("a.xhtml", "t4", None),)


def test_leading_files_are_their_own_chapters():
    spine = ["cover.xhtml", "p0.xhtml", "a.xhtml"]
    out = plan_chapters(spine, [("Ch", "a.xhtml", None)], {})
    assert [p.title for p in out] == ["cover", "p0", "Ch"]
    assert out[0].key == "cover.xhtml"


def test_text_before_first_anchor_is_its_own_chapter():
    out = plan_chapters(["a.xhtml"], [("Ch", "a.xhtml", "t1")], _anch(a=["t1"]))
    assert out[0].title == "a"
    assert out[0].key == "a.xhtml"
    assert out[0].pieces == (Piece("a.xhtml", None, "t1"),)


def test_missing_anchor_starts_at_top():
    out = plan_chapters(["a.xhtml"], [("Ch", "a.xhtml", "gone")], _anch(a=["t1"]))
    assert len(out) == 1
    assert out[0].key == "a.xhtml"
    assert out[0].pieces == (Piece("a.xhtml", None, None),)


def test_duplicate_start_keeps_first_title():
    toc = [("First", "a.xhtml", None), ("Second", "a.xhtml", None)]
    out = plan_chapters(["a.xhtml"], toc, {})
    assert [p.title for p in out] == ["First"]


def test_off_spine_entry_appended():
    toc = [("One", "a.xhtml", None), ("Extra", "z.xhtml", "x")]
    out = plan_chapters(["a.xhtml"], toc, _anch(z=["x"]))
    assert out[-1].title == "Extra"
    assert out[-1].key == "z.xhtml#x"
    assert out[-1].pieces == (Piece("z.xhtml", "x", None),)


HTML = (
    "<body><p id='a'>1</p><div id='w'><p>2</p><p>3</p></div>"
    "<p><span id='s'>4</span></p><p id='e'>5</p></body>"
)


def _texts(tags):
    return [t.get_text() for t in tags]


def test_units_between_anchors():
    soup = BeautifulSoup(HTML, "html.parser")
    assert _texts(units(soup, "a", "e")) == ["1", "2", "3", "4"]
    assert _texts(units(soup, "e", None)) == ["5"]
    assert len(units(soup, None, None)) == 5


def test_anchor_inside_paragraph_starts_with_that_paragraph():
    soup = BeautifulSoup(HTML, "html.parser")
    assert _texts(units(soup, "s", None)) == ["4", "5"]
    assert _texts(units(soup, None, "s")) == ["1", "2", "3"]


def test_anchor_on_wrapping_div_includes_its_paragraphs():
    soup = BeautifulSoup(HTML, "html.parser")
    assert _texts(units(soup, "w", "s")) == ["2", "3"]


def test_svg_image_is_a_unit():
    soup = BeautifulSoup(
        "<p id='a'>x</p><svg id='i'><image xlink:href='p.jpg'/></svg><p id='b'>y</p>",
        "html.parser",
    )
    got = units(soup, "i", "b")
    assert [t.name for t in got] == ["image"]
