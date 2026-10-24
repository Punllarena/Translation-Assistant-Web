"""Chapter caps and linear-time cutting for hostile EPUBs: one file holding thousands of TOC
anchors must not cost O(chapters x file size). Made-up text only."""
import io
import time
import zipfile

import pytest

from api.core.epub_read import extract_chapter_content, open_book
from api.core.epub_safety import MAX_CHAPTERS, EpubError
from tests.test_core_epub import _CONTAINER_XML
from tests.test_epub_api import upload

_OPF = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Anchors</dc:title></metadata>
<manifest>
<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
<item id="big" href="text/big.xhtml" media-type="application/xhtml+xml"/>
</manifest>
<spine><itemref idref="big"/></spine>
</package>
"""


def anchored_book(paras: int, toc: list[int]) -> bytes:
    """One file of ``paras`` anchored paragraphs; the TOC points at the ``toc`` anchors."""
    body = "".join(f'<p id="a{n}">Line {n} of the long file.</p>' for n in range(paras))
    links = "".join(f'<li><a href="text/big.xhtml#a{n}">Part {n}</a></li>' for n in toc)
    nav = (f'<html xmlns:epub="http://www.idpf.org/2007/ops"><body><nav epub:type="toc"><ol>'
           f"{links}</ol></nav></body></html>")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("META-INF/container.xml", _CONTAINER_XML)
        zf.writestr("OEBPS/content.opf", _OPF)
        zf.writestr("OEBPS/nav.xhtml", nav)
        zf.writestr("OEBPS/text/big.xhtml", f"<html><body>{body}</body></html>")
    return buf.getvalue()


def test_many_anchors_in_one_file_open_and_extract_quickly():
    # with the (empty) text before a0 that is exactly the cap; the last runs to the end
    toc = list(range(2, 2 * MAX_CHAPTERS, 2))
    data = anchored_book(2000, toc)
    began = time.monotonic()
    book = open_book(io.BytesIO(data))
    assert len(book["chapters"]) == len(toc) + 1  # a0 and a1 come first
    soups: dict = {}
    texts = [extract_chapter_content(io.BytesIO(data), c["pieces"], soups=soups)[0]
             for c in book["chapters"]]
    assert time.monotonic() - began < 5
    assert texts[1].splitlines() == [f"Line {n} of the long file." for n in range(2, 4)]
    assert sum(len(t.splitlines()) for t in texts) == 2000


def test_too_many_planned_chapters_is_refused():
    with pytest.raises(EpubError, match=f"more than {MAX_CHAPTERS} chapters"):
        open_book(io.BytesIO(anchored_book(2000, list(range(MAX_CHAPTERS + 1)))))


def test_a_huge_toc_is_refused_before_planning():
    toc = [0] * (4 * MAX_CHAPTERS + 1)  # one chapter, but too many entries to read
    with pytest.raises(EpubError, match=f"more than {MAX_CHAPTERS} chapters"):
        open_book(io.BytesIO(anchored_book(1, toc)))


@pytest.mark.parametrize("toc", [list(range(MAX_CHAPTERS + 1)), [0] * (4 * MAX_CHAPTERS + 1)])
def test_inspect_refuses_over_the_caps(app_client, me, toc):
    r = app_client.post("/epub/inspect", files=upload(anchored_book(MAX_CHAPTERS + 1, toc)))
    assert r.status_code == 422
    assert f"more than {MAX_CHAPTERS} chapters" in r.json()["detail"]
