"""open_book / extract_chapter_content split chapters at table-of-contents anchors."""
import zipfile

from api.core import epub_read
from api.core.epub_read import _toc_entry, extract_chapter_content, open_book
from api.core.text import build_new_file, parse_file_content
from tests.fixtures import epub as fx
from tests.test_core_epub import _make_epub3


def _chapter(book: dict, title: str) -> dict:
    return next(c for c in book["chapters"] if c["title"] == title)


def _lines(paras: list[str]) -> int:
    return len(parse_file_content(build_new_file("\n".join(paras)))[0])


def test_chapters_follow_toc_titles(tmp_path):
    book = open_book(fx.split_book(tmp_path))
    assert [c["title"] for c in book["chapters"]] == [
        "cover", "plate1", "plate2", "plate3", "toc",
        "Prologue", "Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4",
    ]
    assert [c["order"] for c in book["chapters"]] == list(range(1, 11))
    assert _chapter(book, "Prologue")["href"] == "OEBPS/text/p6.xhtml#t1"


def test_mid_chapter_image_stays_inline(tmp_path):
    path = fx.split_book(tmp_path)
    prologue = _chapter(open_book(path), "Prologue")
    text, images = extract_chapter_content(path, prologue["pieces"])
    assert text == "\n".join(fx.P6_PARAS + fx.P8_PROLOGUE)
    assert [i["src_path"] for i in images] == ["OEBPS/images/inline.jpg"]
    assert images[0]["anchor_position"] == _lines(fx.P6_PARAS)
    assert prologue["image_count"] == 1
    assert prologue["char_count"] == sum(map(len, fx.P6_PARAS + fx.P8_PROLOGUE))


def test_off_toc_text_continues_previous_chapter(tmp_path):
    path = fx.split_book(tmp_path)
    text, images = extract_chapter_content(path, _chapter(open_book(path), "Chapter 1")["pieces"])
    assert text == "\n".join(fx.P8_CH1 + fx.P9_PARAS)
    assert images == []


def test_three_chapters_in_one_file(tmp_path):
    path = fx.split_book(tmp_path)
    book = open_book(path)
    texts = [
        extract_chapter_content(path, _chapter(book, t)["pieces"])[0]
        for t in ("Chapter 2", "Chapter 3", "Chapter 4")
    ]
    assert texts == ["\n".join(fx.P10_CH2), "\n".join(fx.P10_CH3), "\n".join(fx.P10_CH4)]


def test_plates_are_image_only(tmp_path):
    book = open_book(fx.split_book(tmp_path))
    for title in ("cover", "plate1", "plate2", "plate3"):
        chapter = _chapter(book, title)
        assert chapter["image_only"] is True
        assert (chapter["image_count"], chapter["char_count"]) == (1, 0)
    assert _chapter(book, "Prologue")["image_only"] is False
    assert _chapter(book, "toc")["image_only"] is False


def test_empty_nested_entry_dropped(tmp_path):
    book = open_book(fx.split_book(tmp_path))
    titles = [c["title"] for c in book["chapters"]]
    assert "Part 1" not in titles and "p10" not in titles
    assert "p6" not in titles  # nothing before the Prologue's anchor either


def test_plain_book_is_unchanged(tmp_path):
    path = _make_epub3(tmp_path)
    book = open_book(path)
    assert [(c["title"], c["href"]) for c in book["chapters"]] == [
        ("Chapter 1", "OEBPS/text/ch1.xhtml"), ("Chapter 2", "OEBPS/text/ch2.xhtml"),
    ]
    assert extract_chapter_content(path, "OEBPS/text/ch1.xhtml")[0] == "Hello world."
    assert extract_chapter_content(path, book["chapters"][1]["pieces"])[0] == "More text here."


def test_toc_fragment_is_percent_decoded():
    assert _toc_entry("T", "OEBPS", "p.xhtml#ch%201")[2] == "ch 1"


def test_soup_cache_parses_a_shared_file_once(tmp_path, monkeypatch):
    path = fx.split_book(tmp_path)
    book = open_book(path)
    reads: list[str] = []
    real = epub_read.read_text

    def spy(zf, p, *rest):
        reads.append(p)
        return real(zf, p, *rest)

    monkeypatch.setattr(epub_read, "read_text", spy)
    soups: dict = {}
    extract_chapter_content(path, _chapter(book, "Prologue")["pieces"], soups=soups)
    assert list(soups) == ["OEBPS/text/p8.xhtml"]  # only the last file is kept
    reads.clear()
    for title in ("Chapter 1", "Chapter 2", "Chapter 3", "Chapter 4"):
        cached = extract_chapter_content(path, _chapter(book, title)["pieces"], soups=soups)
        assert cached == extract_chapter_content(path, _chapter(book, title)["pieces"])
    assert reads.count("OEBPS/text/p8.xhtml") == 1  # uncached only; cached hit the Prologue's
    assert reads.count("OEBPS/text/p10.xhtml") == 1 + 3  # once cached, three times uncached
    assert list(soups) == ["OEBPS/text/p10.xhtml"]


def test_a_cached_file_is_charged_once(tmp_path):
    path = fx.split_book(tmp_path)
    book = open_book(path)
    budget, soups = [10**6], {}
    for title in ("Chapter 2", "Chapter 3", "Chapter 4"):
        extract_chapter_content(path, _chapter(book, title)["pieces"], budget, soups)
    with zipfile.ZipFile(path) as zf:
        assert budget == [10**6 - zf.getinfo("OEBPS/text/p10.xhtml").file_size]
