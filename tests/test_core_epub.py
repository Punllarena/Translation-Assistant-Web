"""
Tests for api.core.epub_read/epub_build (desktop tests/test_epub.py plus archive safety):
pure unit tests against synthetic EPUB fixtures built with zipfile. No dependency on the real sample files
in EPUB/ (gitignored, purchased content, manual-testing only).
"""
import io
import zipfile
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from api.core.epub_build import build_epub
from api.core.epub_read import (
    MAX_UNCOMPRESSED,
    EpubError,
    extract_chapter_content,
    open_book,
)

_CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_OPF_EPUB3 = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Test Volume</dc:title>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
<item id="ch2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine>
<itemref idref="ch1"/>
<itemref idref="ch2"/>
</spine>
</package>
"""

_NAV_XHTML = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
<nav epub:type="toc">
<ol>
<li><a href="text/ch1.xhtml">Chapter 1</a></li>
<li><a href="text/ch2.xhtml">Chapter 2</a></li>
</ol>
</nav>
</body>
</html>
"""


def _make_epub3(tmp_path: Path, *, ch1_body="<p>Hello world.</p>", ch2_body="<p>More text here.</p>") -> Path:
    path = tmp_path / "test.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF_EPUB3)
        zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML)
        zf.writestr("OEBPS/text/ch1.xhtml", f"<html><body>{ch1_body}</body></html>")
        zf.writestr("OEBPS/text/ch2.xhtml", f"<html><body>{ch2_body}</body></html>")
    return path


class TestOpenBookEpub3:
    def test_title(self, tmp_path):
        book = open_book(_make_epub3(tmp_path))
        assert book["title"] == "Test Volume"

    def test_chapter_order_and_titles(self, tmp_path):
        book = open_book(_make_epub3(tmp_path))
        assert [c["title"] for c in book["chapters"]] == ["Chapter 1", "Chapter 2"]
        assert [c["order"] for c in book["chapters"]] == [1, 2]

    def test_chapter_href_resolved(self, tmp_path):
        book = open_book(_make_epub3(tmp_path))
        assert book["chapters"][0]["href"] == "OEBPS/text/ch1.xhtml"

    def test_char_count(self, tmp_path):
        book = open_book(_make_epub3(tmp_path, ch1_body="<p>Hello world.</p>"))
        assert book["chapters"][0]["char_count"] == len("Hello world.")

    def test_not_a_zip_raises(self, tmp_path):
        path = tmp_path / "bad.epub"
        path.write_text("not a zip")
        with pytest.raises(EpubError):
            open_book(path)

    def test_missing_container_xml_raises(self, tmp_path):
        path = tmp_path / "bad.epub"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
        with pytest.raises(EpubError):
            open_book(path)


_NAV_NESTED = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
<nav epub:type="toc">
<ol>
<li><a href="text/ch1.xhtml">Part 1</a>
  <ol>
    <li><a href="text/ch1.xhtml#s1">Section 1</a></li>
    <li><a href="text/ch1.xhtml#s2">Section 2</a></li>
  </ol>
</li>
<li><a href="text/ch2.xhtml">Part 2</a></li>
</ol>
</nav>
</body>
</html>
"""

_NAV_LANDMARKS_FIRST = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<body>
<nav epub:type="landmarks">
<ol>
<li><a epub:type="cover" href="text/ch2.xhtml">Cover</a></li>
</ol>
</nav>
<nav epub:type="toc">
<ol>
<li><a href="text/ch1.xhtml">Chapter 1</a></li>
<li><a href="text/ch2.xhtml">Chapter 2</a></li>
</ol>
</nav>
</body>
</html>
"""


def _make_epub3_with_nav(tmp_path: Path, nav_xhtml: str, name: str = "navtest.epub") -> Path:
    path = tmp_path / name
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF_EPUB3)
        zf.writestr("OEBPS/nav.xhtml", nav_xhtml)
        zf.writestr("OEBPS/text/ch1.xhtml", "<html><body><p>One.</p></body></html>")
        zf.writestr("OEBPS/text/ch2.xhtml", "<html><body><p>Two.</p></body></html>")
    return path


class TestNavQuirks:
    def test_nested_toc_entries_deduped_to_one_chapter_per_file(self, tmp_path):
        """Part -> Section#fragment must not yield 3 chapters all pointing at ch1."""
        book = open_book(_make_epub3_with_nav(tmp_path, _NAV_NESTED))
        hrefs = [c["href"] for c in book["chapters"]]
        assert hrefs.count("OEBPS/text/ch1.xhtml") == 1
        assert hrefs == ["OEBPS/text/ch1.xhtml", "OEBPS/text/ch2.xhtml"]
        assert [c["title"] for c in book["chapters"]] == ["Part 1", "Part 2"]

    def test_dedupe_renumbers_order_contiguously(self, tmp_path):
        book = open_book(_make_epub3_with_nav(tmp_path, _NAV_NESTED))
        assert [c["order"] for c in book["chapters"]] == [1, 2]

    def test_toc_nav_preferred_over_earlier_landmarks_nav(self, tmp_path):
        """A landmarks <nav> listed first must not shadow the real toc."""
        book = open_book(_make_epub3_with_nav(tmp_path, _NAV_LANDMARKS_FIRST))
        assert [c["title"] for c in book["chapters"]] == ["Chapter 1", "Chapter 2"]

    def test_untyped_nav_still_used_as_fallback(self, tmp_path):
        """EPUB2-ish nav docs omitting epub:type must still work."""
        nav = _NAV_XHTML.replace('<nav epub:type="toc">', "<nav>")
        book = open_book(_make_epub3_with_nav(tmp_path, nav))
        assert [c["title"] for c in book["chapters"]] == ["Chapter 1", "Chapter 2"]


_OPF_EPUB2 = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Test Volume EPUB2</dc:title>
</metadata>
<manifest>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine toc="ncx">
<itemref idref="ch1"/>
</spine>
</package>
"""

_TOC_NCX = """<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
<navMap>
<navPoint id="np1"><navLabel><text>Chapter 1</text></navLabel><content src="text/ch1.xhtml"/></navPoint>
</navMap>
</ncx>
"""


def _make_epub2(tmp_path: Path) -> Path:
    path = tmp_path / "test2.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF_EPUB2)
        zf.writestr("OEBPS/toc.ncx", _TOC_NCX)
        zf.writestr("OEBPS/text/ch1.xhtml", "<html><body><p>Hello.</p></body></html>")
    return path


class TestOpenBookEpub2:
    def test_title(self, tmp_path):
        book = open_book(_make_epub2(tmp_path))
        assert book["title"] == "Test Volume EPUB2"

    def test_chapter_from_ncx(self, tmp_path):
        book = open_book(_make_epub2(tmp_path))
        assert [c["title"] for c in book["chapters"]] == ["Chapter 1"]
        assert book["chapters"][0]["href"] == "OEBPS/text/ch1.xhtml"


def _make_chapter_epub(tmp_path: Path, body: str) -> tuple[Path, str]:
    """Single-chapter EPUB3 fixture; returns (path, resolved chapter href)."""
    path = tmp_path / "chapter_test.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF_EPUB3)
        zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML)
        zf.writestr("OEBPS/text/ch1.xhtml", f"<html><body>{body}</body></html>")
        zf.writestr("OEBPS/text/ch2.xhtml", "<html><body><p>Filler.</p></body></html>")
    return path, "OEBPS/text/ch1.xhtml"


class TestExtractChapterText:
    def test_plain_paragraphs_joined_by_newline(self, tmp_path):
        path, href = _make_chapter_epub(tmp_path, "<p>First.</p><p>Second.</p>")
        assert extract_chapter_content(path, href)[0] == "First.\nSecond."

    def test_ruby_flattened_to_base_reading(self, tmp_path):
        body = "<p><ruby>漢字<rt>かんじ</rt></ruby>です。</p>"
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "漢字(かんじ)です。"

    def test_gaiji_img_alt_folded_into_text(self, tmp_path):
        body = '<p>あ<img class="gaiji-line" src="g.png" alt="〜"/>い</p>'
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "あ〜い"

    def test_standalone_illustration_paragraph_skipped(self, tmp_path):
        body = '<p>Before.</p><p><img class="fit" src="pic.png"/></p><p>After.</p>'
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "Before.\nAfter."

    def test_ruby_nested_inside_span(self, tmp_path):
        body = '<p><span class="tcy"><ruby>漢字<rt>かんじ</rt></ruby></span></p>'
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "漢字(かんじ)"

    def test_no_paragraphs_returns_empty_string(self, tmp_path):
        path, href = _make_chapter_epub(tmp_path, "<div>No p tags here</div>")
        assert extract_chapter_content(path, href)[0] == ""


def _make_illustration_epub(tmp_path: Path, body: str) -> tuple[Path, str]:
    path = tmp_path / "illust.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF_EPUB3)
        zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML)
        zf.writestr("OEBPS/text/ch1.xhtml", f"<html><body>{body}</body></html>")
        zf.writestr("OEBPS/text/ch2.xhtml", "<html><body><p>Filler.</p></body></html>")
        zf.writestr("OEBPS/images/pic1.png", b"fake-png-1")
        zf.writestr("OEBPS/images/pic2.png", b"fake-png-2")
    return path, "OEBPS/text/ch1.xhtml"


class TestExtractChapterContent:
    def test_text_matches_extract_chapter_text_equivalent(self, tmp_path):
        path, href = _make_illustration_epub(tmp_path, "<p>First.</p><p>Second.</p>")
        text, images = extract_chapter_content(path, href)
        assert text == "First.\nSecond."
        assert images == []

    def test_illustration_after_single_sentence_paragraph(self, tmp_path):
        body = '<p>Before.</p><p><img class="fit" src="../images/pic1.png"/></p><p>After.</p>'
        path, href = _make_illustration_epub(tmp_path, body)
        text, images = extract_chapter_content(path, href)
        assert text == "Before.\nAfter."
        assert len(images) == 1
        assert images[0]["anchor_position"] == 1  # after "Before." -> 1 raw_line
        assert images[0]["src_path"] == "OEBPS/images/pic1.png"
        assert images[0]["data"] == b"fake-png-1"

    def test_anchor_position_accounts_for_sentence_splitting(self, tmp_path):
        # "First.Second." (one paragraph, two sentences) splits into 2 raw_lines
        # via build_new_file's 。-splitting -- the image after it must anchor at 2, not 1.
        body = '<p>First。Second。</p><p><img class="fit" src="../images/pic1.png"/></p><p>Third.</p>'
        path, href = _make_illustration_epub(tmp_path, body)
        text, images = extract_chapter_content(path, href)
        assert len(images) == 1
        assert images[0]["anchor_position"] == 2

    def test_two_illustrations_no_text_between(self, tmp_path):
        body = (
            '<p>Before.</p>'
            '<p><img class="fit" src="../images/pic1.png"/></p>'
            '<p><img class="fit" src="../images/pic2.png"/></p>'
            '<p>After.</p>'
        )
        path, href = _make_illustration_epub(tmp_path, body)
        text, images = extract_chapter_content(path, href)
        assert text == "Before.\nAfter."
        assert len(images) == 2
        assert images[0]["anchor_position"] == images[1]["anchor_position"] == 1
        assert images[0]["src_path"] == "OEBPS/images/pic1.png"
        assert images[1]["src_path"] == "OEBPS/images/pic2.png"

    def test_illustration_at_start_of_chapter(self, tmp_path):
        body = '<p><img class="fit" src="../images/pic1.png"/></p><p>Only text.</p>'
        path, href = _make_illustration_epub(tmp_path, body)
        text, images = extract_chapter_content(path, href)
        assert text == "Only text."
        assert images[0]["anchor_position"] == 0

    def test_illustration_at_end_of_chapter(self, tmp_path):
        body = '<p>Only text.</p><p><img class="fit" src="../images/pic1.png"/></p>'
        path, href = _make_illustration_epub(tmp_path, body)
        text, images = extract_chapter_content(path, href)
        assert text == "Only text."
        assert images[0]["anchor_position"] == 1

    def test_missing_image_bytes_skipped_not_fatal(self, tmp_path):
        body = '<p>Before.</p><p><img class="fit" src="../images/missing.png"/></p><p>After.</p>'
        path, href = _make_illustration_epub(tmp_path, body)
        text, images = extract_chapter_content(path, href)
        assert text == "Before.\nAfter."
        assert images == []  # broken manifest reference -- caught, chapter import continues


_SVG_PAGE = (
    '<div class="main"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1257 1920">'
    '<image width="1257" height="1920" xlink:href="../images/pic1.png"/></svg></div>'
)


class TestSvgIllustration:
    """Fixed-layout colour plates use <svg><image>, not <p><img>."""

    def test_svg_image_extracted(self, tmp_path):
        path, href = _make_illustration_epub(tmp_path, _SVG_PAGE)
        text, images = extract_chapter_content(path, href)
        assert text == ""
        assert len(images) == 1
        assert images[0]["src_path"] == "OEBPS/images/pic1.png"
        assert images[0]["data"] == b"fake-png-1"

    def test_svg2_plain_href_also_accepted(self, tmp_path):
        body = '<svg viewBox="0 0 10 10"><image href="../images/pic2.png"/></svg>'
        path, href = _make_illustration_epub(tmp_path, body)
        _, images = extract_chapter_content(path, href)
        assert [i["src_path"] for i in images] == ["OEBPS/images/pic2.png"]

    def test_svg_image_anchors_after_preceding_text(self, tmp_path):
        path, href = _make_illustration_epub(tmp_path, f"<p>Before.</p>{_SVG_PAGE}<p>After.</p>")
        text, images = extract_chapter_content(path, href)
        assert text == "Before.\nAfter."
        assert images[0]["anchor_position"] == 1

    def test_image_count_reported_by_open_book(self, tmp_path):
        path, _ = _make_illustration_epub(tmp_path, _SVG_PAGE)
        book = open_book(path)
        by_href = {c["href"]: c for c in book["chapters"]}
        assert by_href["OEBPS/text/ch1.xhtml"]["image_count"] == 1
        assert by_href["OEBPS/text/ch2.xhtml"]["image_count"] == 0


_OPF_SPINE_EXTRAS = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Test Volume</dc:title>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="plate" href="text/p-fmatter-003.xhtml" media-type="application/xhtml+xml"/>
<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
<item id="ch2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine>
<itemref idref="nav"/>
<itemref idref="plate"/>
<itemref idref="ch1"/>
<itemref idref="ch2"/>
</spine>
</package>
"""


def _make_epub_with_spine_extras(tmp_path: Path) -> Path:
    path = tmp_path / "spine.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF_SPINE_EXTRAS)
        zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML)
        zf.writestr("OEBPS/text/p-fmatter-003.xhtml", f"<html><body>{_SVG_PAGE}</body></html>")
        zf.writestr("OEBPS/text/ch1.xhtml", "<html><body><p>Hello world.</p></body></html>")
        zf.writestr("OEBPS/text/ch2.xhtml", "<html><body><p>More text.</p></body></html>")
        zf.writestr("OEBPS/images/pic1.png", b"fake-png-1")
    return path


class TestSpineOnlyPages:
    def test_page_missing_from_toc_is_listed(self, tmp_path):
        book = open_book(_make_epub_with_spine_extras(tmp_path))
        hrefs = [c["href"] for c in book["chapters"]]
        assert hrefs == [
            "OEBPS/text/p-fmatter-003.xhtml",  # spine order, ahead of the TOC entries
            "OEBPS/text/ch1.xhtml",
            "OEBPS/text/ch2.xhtml",
        ]

    def test_off_toc_page_titled_after_its_file(self, tmp_path):
        book = open_book(_make_epub_with_spine_extras(tmp_path))
        assert book["chapters"][0]["title"] == "p-fmatter-003"
        assert book["chapters"][1]["title"] == "Chapter 1"  # TOC title still wins

    def test_nav_document_not_listed_as_a_chapter(self, tmp_path):
        book = open_book(_make_epub_with_spine_extras(tmp_path))
        assert "OEBPS/nav.xhtml" not in [c["href"] for c in book["chapters"]]


class TestBoldFlattening:
    def test_bold_span_wrapped_in_markers(self, tmp_path):
        body = '<p><span class="bold">emphasized text</span></p>'
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "**emphasized text**"

    def test_bold_span_mixed_with_plain_text(self, tmp_path):
        body = '<p>Before <span class="bold">bold part</span> after.</p>'
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "Before **bold part** after."

    def test_ruby_inside_bold_span(self, tmp_path):
        body = '<p><span class="bold"><ruby>漢字<rt>かんじ</rt></ruby></span></p>'
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "**漢字(かんじ)**"

    def test_tcy_span_unaffected_by_bold_handling(self, tmp_path):
        body = '<p>A<span class="tcy">!?</span>B</p>'
        path, href = _make_chapter_epub(tmp_path, body)
        assert extract_chapter_content(path, href)[0] == "A!?B"


class TestBuildEpub:
    def test_returns_bytes(self):
        result = build_epub("My Volume", [("Chapter 1", [("text", "Hello."), ("text", "World.")], [])])
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_chapter_with_text_keeps_its_heading(self):
        result = build_epub("My Volume", [("Chapter 1", [("text", "Hello.")], [])])
        with zipfile.ZipFile(io.BytesIO(result)) as zf:
            assert "<h1>Chapter 1</h1>" in zf.read("OEBPS/text/chap1.xhtml").decode("utf-8")

    def test_is_valid_zip(self, tmp_path):
        result = build_epub("My Volume", [("Chapter 1", [("text", "Hello.")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        assert zipfile.is_zipfile(out)

    def test_mimetype_is_first_entry_uncompressed(self, tmp_path):
        result = build_epub("My Volume", [("Chapter 1", [("text", "Hello.")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            info = zf.infolist()[0]
            assert info.filename == "mimetype"
            assert info.compress_type == zipfile.ZIP_STORED

    def test_round_trip_title_and_chapters(self, tmp_path):
        result = build_epub("My Volume", [
            ("Chapter 1", [("text", "Hello world.")], []),
            ("Chapter 2", [("text", "Second chapter.")], []),
        ])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        book = open_book(out)
        assert book["title"] == "My Volume"
        assert [c["title"] for c in book["chapters"]] == ["Chapter 1", "Chapter 2"]

    def test_round_trip_paragraph_text_survives(self, tmp_path):
        result = build_epub("My Volume", [
            ("Chapter 1", [("text", "Hello world."), ("text", "Second paragraph.")], []),
        ])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        book = open_book(out)
        href = book["chapters"][0]["href"]
        text = extract_chapter_content(out, href)[0]
        assert text == "Hello world.\nSecond paragraph."

    def test_xml_special_characters_escaped(self, tmp_path):
        result = build_epub("My Volume", [("Chapter 1", [("text", "A & B < C > D")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        book = open_book(out)
        href = book["chapters"][0]["href"]
        assert extract_chapter_content(out, href)[0] == "A & B < C > D"


_OPF_EPUB3_COVER = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Test Volume</dc:title>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="cover-img" href="images/cover.jpg" media-type="image/jpeg" properties="cover-image"/>
<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine>
<itemref idref="ch1"/>
</spine>
</package>
"""

_OPF_EPUB2_COVER = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Test Volume</dc:title>
<meta name="cover" content="cover-img"/>
</metadata>
<manifest>
<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
<item id="cover-img" href="images/cover.jpg" media-type="image/jpeg"/>
<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine toc="ncx">
<itemref idref="ch1"/>
</spine>
</package>
"""


def _make_epub_with_cover(tmp_path: Path, opf: str, *, ncx: bool = False) -> Path:
    path = tmp_path / "cover.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", opf)
        if ncx:
            zf.writestr("OEBPS/toc.ncx", _TOC_NCX)
        else:
            zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML.replace(
                '<li><a href="text/ch2.xhtml">Chapter 2</a></li>', ""
            ))
        zf.writestr("OEBPS/images/cover.jpg", b"fake-jpeg-bytes")
        zf.writestr("OEBPS/text/ch1.xhtml", "<html><body><p>Hello.</p></body></html>")
    return path


class TestOpenBookCover:
    def test_epub3_cover_href_resolved(self, tmp_path):
        path = _make_epub_with_cover(tmp_path, _OPF_EPUB3_COVER)
        book = open_book(path)
        assert book["cover_href"] == "OEBPS/images/cover.jpg"

    def test_epub2_cover_meta_fallback(self, tmp_path):
        path = _make_epub_with_cover(tmp_path, _OPF_EPUB2_COVER, ncx=True)
        book = open_book(path)
        assert book["cover_href"] == "OEBPS/images/cover.jpg"

    def test_no_cover_returns_none(self, tmp_path):
        book = open_book(_make_epub3(tmp_path))
        assert book["cover_href"] is None


_OPF_EPUB3_METADATA = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>Test Volume</dc:title>
<dc:creator id="creator01">Author Name</dc:creator>
<meta refines="#creator01" property="role" scheme="marc:relators">aut</meta>
<dc:creator id="creator02">Illustrator Name</dc:creator>
<meta refines="#creator02" property="role" scheme="marc:relators">ill</meta>
<dc:publisher>Test Publisher</dc:publisher>
<dc:identifier id="uid">urn:isbn:1234567890123</dc:identifier>
</metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine>
<itemref idref="ch1"/>
</spine>
</package>
"""


def _make_epub_with_metadata(tmp_path: Path) -> Path:
    path = tmp_path / "metadata.epub"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF_EPUB3_METADATA)
        zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML.replace(
            '<li><a href="text/ch2.xhtml">Chapter 2</a></li>', ""
        ))
        zf.writestr("OEBPS/text/ch1.xhtml", "<html><body><p>Hello.</p></body></html>")
    return path


class TestOpenBookMetadata:
    def test_metadata_role_extraction_survives_void_meta_parsing(self, tmp_path):
        book = open_book(_make_epub_with_metadata(tmp_path))
        assert book["author"] == "Author Name"
        assert book["illustrator"] == "Illustrator Name"

    def test_publisher_and_identifier(self, tmp_path):
        book = open_book(_make_epub_with_metadata(tmp_path))
        assert book["publisher"] == "Test Publisher"
        assert book["identifier"] == "urn:isbn:1234567890123"

    def test_missing_metadata_defaults_empty(self, tmp_path):
        book = open_book(_make_epub3(tmp_path))
        assert book["author"] == ""
        assert book["illustrator"] == ""
        assert book["publisher"] == ""
        assert book["identifier"] == ""

    def test_creator_without_role_meta_defaults_to_author(self, tmp_path):
        opf = _OPF_EPUB3_METADATA.replace(
            '<meta refines="#creator01" property="role" scheme="marc:relators">aut</meta>\n', ""
        )
        path = tmp_path / "no_role.epub"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("mimetype", "application/epub+zip")
            zf.writestr("META-INF/container.xml", _CONTAINER_XML)
            zf.writestr("OEBPS/content.opf", opf)
            zf.writestr("OEBPS/nav.xhtml", _NAV_XHTML.replace(
                '<li><a href="text/ch2.xhtml">Chapter 2</a></li>', ""
            ))
            zf.writestr("OEBPS/text/ch1.xhtml", "<html><body><p>Hello.</p></body></html>")
        book = open_book(path)
        assert book["author"] == "Author Name"


class TestChapterHeadingAndBold:
    def test_chapter_heading_emitted(self, tmp_path):
        result = build_epub("Vol", [("Chapter One", [("text", "Hello.")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            xhtml = zf.read("OEBPS/text/chap1.xhtml").decode("utf-8")
        assert "<h1>Chapter One</h1>" in xhtml
        assert xhtml.index("<h1>") < xhtml.index("<p>Hello.</p>")

    def test_bold_marker_converted_to_b_tag(self, tmp_path):
        result = build_epub("Vol", [("Ch 1", [("text", "Before **bold** after.")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            xhtml = zf.read("OEBPS/text/chap1.xhtml").decode("utf-8")
        assert "Before <b>bold</b> after." in xhtml

    def test_bold_marker_with_special_chars_escaped(self, tmp_path):
        result = build_epub("Vol", [("Ch 1", [("text", "**A & B**")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            xhtml = zf.read("OEBPS/text/chap1.xhtml").decode("utf-8")
        assert "<b>A &amp; B</b>" in xhtml

    def test_no_bold_marker_unaffected(self, tmp_path):
        result = build_epub("Vol", [("Ch 1", [("text", "Plain text.")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            xhtml = zf.read("OEBPS/text/chap1.xhtml").decode("utf-8")
        assert "<p>Plain text.</p>" in xhtml
        assert "<b>" not in xhtml


class TestBuildEpubMetadata:
    def test_creator_and_illustrator_emitted_with_roles(self, tmp_path):
        result = build_epub(
            "Vol", [("Ch 1", [("text", "Hello.")], [])],
            creator="Author Name", illustrator="Illustrator Name",
        )
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "<dc:creator" in opf and "Author Name" in opf
        assert "Illustrator Name" in opf
        assert 'property="role"' in opf

    def test_publisher_emitted(self, tmp_path):
        result = build_epub("Vol", [("Ch 1", [("text", "Hello.")], [])], publisher="Test Publisher")
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "<dc:publisher>Test Publisher</dc:publisher>" in opf

    def test_identifier_used_when_given(self, tmp_path):
        result = build_epub(
            "Vol", [("Ch 1", [("text", "Hello.")], [])], identifier="urn:isbn:1234567890123",
        )
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "urn:isbn:1234567890123" in opf

    def test_blank_metadata_omits_tags(self, tmp_path):
        result = build_epub("Vol", [("Ch 1", [("text", "Hello.")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "<dc:creator" not in opf
        assert "<dc:publisher" not in opf


class TestBuildEpubImages:
    def test_chapter_with_image_round_trips(self, tmp_path):
        content = [("text", "Before."), ("image", "images/pic.png"), ("text", "After.")]
        chapter_images = [{"src_path": "images/pic.png", "data": b"fake-png-bytes"}]
        result = build_epub("Vol", [("Ch 1", content, chapter_images)])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            assert zf.read("OEBPS/images/pic.png") == b"fake-png-bytes"
            xhtml = zf.read("OEBPS/text/chap1.xhtml").decode("utf-8")
        assert '<img src="../images/pic.png"' in xhtml
        assert xhtml.index("Before.") < xhtml.index('<img') < xhtml.index("After.")

    def test_no_images_still_works(self, tmp_path):
        content = [("text", "Hello.")]
        result = build_epub("Vol", [("Ch 1", content, [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        assert zipfile.is_zipfile(out)

    def test_cover_manifest_and_meta(self, tmp_path):
        cover = {"data": b"fake-cover-bytes", "media_type": "image/jpeg"}
        result = build_epub("Vol", [("Ch 1", [("text", "Hello.")], [])], cover=cover)
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            assert zf.read("OEBPS/images/cover.jpg") == b"fake-cover-bytes"
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert 'properties="cover-image"' in opf
        assert '<meta name="cover" content="cover-image"/>' in opf

    def test_no_cover_no_cover_metadata(self, tmp_path):
        result = build_epub("Vol", [("Ch 1", [("text", "Hello.")], [])])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        assert "cover" not in opf

    def test_cover_href_collision_with_chapter_image_disambiguated(self, tmp_path):
        # A chapter's own inline image happens to resolve to the exact same
        # basename the cover would get ("images/cover.jpg" -- a plausible
        # collision since cover fixtures conventionally use that basename).
        # Both must survive as distinct, independently-readable zip entries
        # and distinct manifest hrefs.
        content = [("text", "Before."), ("image", "images/cover.jpg"), ("text", "After.")]
        chapter_images = [{"src_path": "images/cover.jpg", "data": b"chapter-image-bytes"}]
        cover = {"data": b"cover-image-bytes", "media_type": "image/jpeg"}
        result = build_epub("Vol", [("Ch 1", content, chapter_images)], cover=cover)
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            image_entries = [n for n in names if n.startswith("OEBPS/images/")]
            assert len(image_entries) == len(set(image_entries)) == 2
            # The chapter image keeps the natural basename; the cover gets
            # disambiguated since it lost the race (chapters are written first).
            assert zf.read("OEBPS/images/cover.jpg") == b"chapter-image-bytes"
            assert zf.read("OEBPS/images/cover_1.jpg") == b"cover-image-bytes"
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        soup = BeautifulSoup(opf, "html.parser")
        hrefs = [item["href"] for item in soup.find_all("item")]
        assert hrefs.count("images/cover.jpg") == 1
        assert hrefs.count("images/cover_1.jpg") == 1

    def test_image_href_with_quote_does_not_break_xml_attribute(self, tmp_path):
        # src_path can originate from an imported EPUB's internal filenames
        # (attacker-controlled if a malicious EPUB is imported). A `"` in
        # the basename must not let markup escape the href attribute.
        src_path = 'images/pic".png'
        content = [("text", "Before."), ("image", src_path), ("text", "After.")]
        chapter_images = [{"src_path": src_path, "data": b"tricky-bytes"}]
        result = build_epub("Vol", [("Ch 1", content, chapter_images)])
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        # Unescaped, the raw `"` would break out of the href attribute and
        # produce a stray dangling ".png"/> fragment parsed as markup.
        assert '&quot;' in opf
        soup = BeautifulSoup(opf, "html.parser")
        img_items = [item for item in soup.find_all("item") if item.get("id", "").startswith("img")]
        assert len(img_items) == 1
        # The value round-trips as data -- exactly the original href, quote intact.
        assert img_items[0]["href"] == src_path

    def test_cover_media_type_with_quote_does_not_break_xml_attribute(self, tmp_path):
        # cover["media_type"] is caller-supplied, not internally generated.
        cover = {"data": b"cover-bytes", "media_type": 'image/jpeg" foo="bar'}
        result = build_epub("Vol", [("Ch 1", [("text", "Hello.")], [])], cover=cover)
        out = tmp_path / "out.epub"
        out.write_bytes(result)
        with zipfile.ZipFile(out) as zf:
            opf = zf.read("OEBPS/content.opf").decode("utf-8")
        soup = BeautifulSoup(opf, "html.parser")
        cover_item = soup.find("item", id="cover-image")
        assert cover_item is not None
        # No injected "foo" attribute -- the whole string stayed as the
        # media-type attribute's value rather than spawning a new attribute.
        assert cover_item.get("foo") is None
        assert cover_item["media-type"] == 'image/jpeg" foo="bar'
        assert cover_item.get("properties") == "cover-image"


# ---------------------------------------------------------------------------
# Archive safety (ours, spec §6)
# ---------------------------------------------------------------------------

def zipped(entries: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    buf.seek(0)
    return buf


@pytest.mark.parametrize("name", ["../evil.xhtml", "/abs.xhtml", "OEBPS/../../x", "a\\..\\b"])
def test_unsafe_entry_names_are_refused(name):
    with pytest.raises(EpubError, match="unsafe"):
        open_book(zipped({"META-INF/container.xml": b"<container/>", name: b"x"}))


def test_declared_size_over_the_cap_is_refused(monkeypatch):
    monkeypatch.setattr("api.core.epub_read.MAX_UNCOMPRESSED", 10)
    with pytest.raises(EpubError, match="MB"):
        open_book(zipped({"META-INF/container.xml": b"x" * 11}))


def test_not_a_zip_is_an_epub_error():
    with pytest.raises(EpubError):
        open_book(io.BytesIO(b"not a zip"))


def test_extract_chapter_content_refuses_unsafe_and_bad_zips():
    with pytest.raises(EpubError, match="unsafe"):
        extract_chapter_content(zipped({"../x": b"x"}), "c.xhtml")
    with pytest.raises(EpubError):
        extract_chapter_content(io.BytesIO(b"not a zip"), "c.xhtml")


def test_cap_constant():
    assert MAX_UNCOMPRESSED == 256 * 1024 * 1024


# ---------------------------------------------------------------------------
# Hostile but valid zips surface as EpubError only
# ---------------------------------------------------------------------------

_HOSTILE_CONTAINER = (
    b'<container><rootfiles><rootfile full-path="OEBPS/content.opf"/></rootfiles></container>'
)


def test_non_utf8_container_is_an_epub_error():
    with pytest.raises(EpubError, match="UnicodeDecodeError"):
        open_book(zipped({"META-INF/container.xml": b"\xff\xfe\x00bad"}))


def test_nav_item_without_href_is_an_epub_error():
    opf = (
        b'<package><metadata><dc:title>T</dc:title></metadata><manifest>'
        b'<item id="nav" properties="nav" media-type="application/xhtml+xml"/>'
        b"</manifest><spine/></package>"
    )
    with pytest.raises(EpubError, match="KeyError"):
        open_book(zipped({"META-INF/container.xml": _HOSTILE_CONTAINER, "OEBPS/content.opf": opf}))


def test_cover_item_without_href_is_an_epub_error():
    opf = (
        b'<package><metadata><meta name="cover" content="c"/></metadata><manifest>'
        b'<item id="c" media-type="image/png"/></manifest><spine/></package>'
    )
    with pytest.raises(EpubError):
        open_book(zipped({"META-INF/container.xml": _HOSTILE_CONTAINER, "OEBPS/content.opf": opf}))


def test_corrupt_deflate_stream_is_an_epub_error():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("META-INF/container.xml", b"<container/>" * 50)
    raw = bytearray(buf.getvalue())
    raw[54:64] = b"\xff" * 10  # inside the compressed data (local header is 30 + 22 name bytes)
    with pytest.raises(EpubError, match="Not a readable"):
        open_book(io.BytesIO(bytes(raw)))


def test_extract_chapter_non_utf8_is_an_epub_error():
    with pytest.raises(EpubError, match="UnicodeDecodeError"):
        extract_chapter_content(zipped({"c.xhtml": b"\xff\xfe\x00"}), "c.xhtml")
