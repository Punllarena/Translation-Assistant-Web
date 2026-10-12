"""Tests for api/core/scrape.py, ported from the desktop tests/test_scraper.py."""
import httpx
import pytest
from bs4 import BeautifulSoup

from api.core import scrape
from api.core.scrape import _para_text, fetch_series_index, fetch_syosetu


def mock(pages: dict[str, tuple[int, str, dict]]):
    """url -> (status, html, headers)."""
    def handle(request):
        status, html, headers = pages[str(request.url)]
        return httpx.Response(status, text=html, headers=headers)
    return scrape.client(transport=httpx.MockTransport(handle))


def one(url: str, html: str):
    return mock({url: (200, html, {})})


def _p(html: str):
    """Parse a bare <p> tag for use in _para_text tests."""
    return BeautifulSoup(f"<p>{html}</p>", "html.parser").find("p")


_TOC_HTML = """
<html><body>
<div class="p-eplist__sublist">
  <a href="/n7696mg/1/">第一話　始まり</a>
</div>
<div class="p-eplist__sublist">
  <a href="/n7696mg/2/">第二話　出会い</a>
</div>
<div class="p-eplist__sublist">
  <a href="/n7696mg/3/">第三話　決意</a>
</div>
</body></html>
"""

_TOC_HTML_OLD = """
<html><body>
<div class="index_box">
  <dl class="novel_sublist2">
    <dd class="subtitle"><a href="/n7696mg/1/">第一話　始まり</a></dd>
    <dd class="subtitle"><a href="/n7696mg/2/">第二話　出会い</a></dd>
    <dd class="subtitle"><a href="/n7696mg/3/">第三話　決意</a></dd>
  </dl>
</div>
</body></html>
"""


def test_fetch_series_index_rejects_chapter_url():
    with one("https://ncode.syosetu.com/n7696mg/1/", "") as c:
        with pytest.raises(ValueError, match="series root"):
            fetch_series_index(c, "https://ncode.syosetu.com/n7696mg/1/")


def test_fetch_series_index_rejects_non_syosetu():
    with one("https://example.com/n7696mg/", "") as c:
        with pytest.raises(ValueError):
            fetch_series_index(c, "https://example.com/n7696mg/")


def test_fetch_series_index_parses_chapters():
    url = "https://novel18.syosetu.com/n7696mg/"
    with one(url, _TOC_HTML) as c:
        chapters = fetch_series_index(c, url)

    assert len(chapters) == 3
    assert chapters[0] == {
        "num": 1,
        "title": "第一話　始まり",
        "url": "https://novel18.syosetu.com/n7696mg/1/",
    }
    assert chapters[2]["num"] == 3
    assert chapters[2]["title"] == "第三話　決意"


def test_fetch_series_index_parses_chapters_old_format():
    url = "https://novel18.syosetu.com/n7696mg/"
    with one(url, _TOC_HTML_OLD) as c:
        chapters = fetch_series_index(c, url)

    assert len(chapters) == 3
    assert chapters[0] == {
        "num": 1,
        "title": "第一話　始まり",
        "url": "https://novel18.syosetu.com/n7696mg/1/",
    }


def test_fetch_series_index_follows_pagination():
    page1_html = """
<html><body>
<div class="p-eplist__sublist"><a href="/n0280z/1/">第一話</a></div>
<div class="p-eplist__sublist"><a href="/n0280z/2/">第二話</a></div>
<a class="c-pager__item c-pager__item--next" href="/n0280z/?p=2">次へ</a>
</body></html>
"""
    page2_html = """
<html><body>
<div class="p-eplist__sublist"><a href="/n0280z/3/">第三話</a></div>
</body></html>
"""
    base = "https://novel18.syosetu.com/n0280z/"
    with mock({base: (200, page1_html, {}), base + "?p=2": (200, page2_html, {})}) as c:
        chapters = fetch_series_index(c, base)

    assert len(chapters) == 3
    assert [ch["num"] for ch in chapters] == [1, 2, 3]


def test_fetch_series_index_empty_toc():
    url = "https://ncode.syosetu.com/n1234ab/"
    with one(url, "<html><body></body></html>") as c:
        assert fetch_series_index(c, url) == []


class TestParaText:
    def test_plain_text_unchanged(self):
        assert _para_text(_p("普通のテキスト")) == "普通のテキスト"

    def test_ruby_rendered_as_parenthesis(self):
        assert _para_text(_p("<ruby>文章<rt>ぶんしょう</rt></ruby>")) == "文章(ぶんしょう)"

    def test_ruby_with_rb_tag(self):
        assert _para_text(_p("<ruby><rb>漢字</rb><rt>かんじ</rt></ruby>")) == "漢字(かんじ)"

    def test_ruby_without_rt_emits_base_only(self):
        assert _para_text(_p("<ruby>テスト</ruby>")) == "テスト"

    def test_ruby_inline_with_surrounding_text(self):
        result = _para_text(_p("彼は<ruby>魔王<rt>まおう</rt></ruby>だ"))
        assert result == "彼は魔王(まおう)だ"

    def test_multiple_ruby_in_one_paragraph(self):
        result = _para_text(_p(
            "<ruby>山<rt>やま</rt></ruby>と<ruby>川<rt>かわ</rt></ruby>"
        ))
        assert result == "山(やま)と川(かわ)"

    def test_empty_paragraph(self):
        assert _para_text(_p("")) == ""

    def test_rp_tags_ignored(self):
        result = _para_text(_p("<ruby>漢<rp>(</rp><rt>かん</rt><rp>)</rp></ruby>"))
        assert result == "漢(かん)"


_CHAPTER_HTML_RUBY = """
<html><body>
<h1 class="p-novel__title--rensai">第一話　始まり</h1>
<div class="js-novel-text p-novel__text">
  <p>彼は<ruby>魔王<rt>まおう</rt></ruby>だった。</p>
  <p>普通のテキスト</p>
</div>
</body></html>
"""


def test_fetch_syosetu_renders_ruby_as_parenthesis():
    url = "https://ncode.syosetu.com/n1234ab/1/"
    with one(url, _CHAPTER_HTML_RUBY) as c:
        title, content = fetch_syosetu(c, url)

    assert title == "第一話　始まり"
    assert "魔王(まおう)" in content
    assert "普通のテキスト" in content


def test_fetch_syosetu_without_novel_text_is_a_value_error():
    url = "https://ncode.syosetu.com/n1234ab/1/"
    with one(url, "<html></html>") as c, pytest.raises(ValueError, match="novel text"):
        fetch_syosetu(c, url)


@pytest.mark.parametrize("url", [
    "https://x.syosetu.com@evil.com/n1/1/", "http://localhost/n1/1/",
    "file:///etc/passwd", "https://evil.com/?.syosetu.com", "ftp://ncode.syosetu.com/n1/1/",
])
def test_only_syosetu_urls_are_accepted(url):
    with pytest.raises(ValueError):
        scrape.validate_url(url)


def test_a_redirect_off_syosetu_is_refused_before_it_is_followed():
    seen = []

    def handle(request):
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/latest"})
    with scrape.client(transport=httpx.MockTransport(handle)) as c, pytest.raises(ValueError):
        scrape.fetch_syosetu(c, "https://ncode.syosetu.com/n1/1/")
    assert seen == ["https://ncode.syosetu.com/n1/1/"]


def test_http_errors_become_scrape_errors_naming_the_status():
    with mock({"https://ncode.syosetu.com/n1/1/": (503, "", {})}) as c:
        with pytest.raises(scrape.ScrapeError, match="503"):
            scrape.fetch_syosetu(c, "https://ncode.syosetu.com/n1/1/")


def test_index_pages_are_capped(monkeypatch):
    monkeypatch.setattr(scrape, "MAX_INDEX_PAGES", 3)
    page = ('<div class="p-eplist__sublist"><a href="/n1/1/">a</a></div>'
            '<a class="c-pager__item c-pager__item--next" href="/n1/?p=2">next</a>')
    with mock({u: (200, page, {}) for u in [
        "https://ncode.syosetu.com/n1/", "https://ncode.syosetu.com/n1/?p=2"]}) as c:
        with pytest.raises(scrape.ScrapeError, match="pages"):
            scrape.fetch_series_index(c, "https://ncode.syosetu.com/n1/")


def test_throttle_spaces_calls(monkeypatch):
    clock = [100.0]
    slept = []
    monkeypatch.setattr(scrape.time, "monotonic", lambda: clock[0])

    def sleep(s):
        slept.append(s)
        clock[0] += s
    monkeypatch.setattr(scrape.time, "sleep", sleep)
    monkeypatch.setattr(scrape, "_last", 0.0)
    scrape.throttle(5)
    clock[0] += 1
    scrape.throttle(5)
    assert slept == [4.0]
