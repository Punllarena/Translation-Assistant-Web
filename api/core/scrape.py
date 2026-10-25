"""Syosetu fetching, from the desktop translation_assistant/scraper.py: URL checks and
the fetch_* functions. The QThread workers are gone (the jobs worker replaces them).
HTTP goes through an injected httpx.Client so tests replay recorded HTML (spec §12)."""

import re
import threading
import time
from datetime import datetime
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup

_ALLOWED_SUFFIX = ".syosetu.com"
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
TIMEOUT = 10
MAX_INDEX_PAGES = 100  # ours: a next-link loop must not run forever


class ScrapeError(Exception):
    """Syosetu could not be reached or answered with an error."""


class NoChapters(ScrapeError):
    """The page has neither chapter entries nor novel text."""


def validate_url(url: str) -> None:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise ValueError("The URL contains control characters")
    try:
        httpx.URL(url)  # what httpx would refuse later (e.g. a non-IDNA host) is a 422, not a 500
    except httpx.InvalidURL as exc:
        raise ValueError(f"Not a valid URL: {exc}") from exc
    # hostname, not the desktop's netloc: "x.syosetu.com@evil.com" has that netloc suffix
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in ("http", "https") or not host.endswith(_ALLOWED_SUFFIX):
        raise ValueError("Only syosetu.com URLs are supported")


def _check_request(request: httpx.Request) -> None:
    validate_url(str(request.url))  # every hop, redirects included, before it is sent


def client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        transport=transport, timeout=TIMEOUT, follow_redirects=True,
        headers={"User-Agent": _UA}, cookies={"over18": "yes"},
        event_hooks={"request": [_check_request]},
    )


def _get(c: httpx.Client, url: str) -> str:
    validate_url(url)
    try:
        r = c.get(url)
    except httpx.InvalidURL as exc:
        raise ValueError(f"Not a valid URL: {exc}") from exc
    except httpx.HTTPError as exc:
        host = urlparse(url).hostname
        raise ScrapeError(f"could not reach {host} ({type(exc).__name__})") from exc
    if r.status_code != 200:
        raise ScrapeError(f"{urlparse(url).hostname} answered HTTP {r.status_code}")
    return r.text


_lock = threading.Lock()
_last = 0.0


def throttle(delay: float) -> None:
    """Space chapter requests at least ``delay`` seconds apart, process-wide, so
    concurrent jobs cannot defeat the desktop's rate limit (spec §9)."""
    global _last
    with _lock:
        wait = _last + delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last = time.monotonic()


def _para_text(p) -> str:
    """Extract text from a <p> tag, rendering <ruby> as base(reading)."""
    parts = []
    for node in p.children:
        if hasattr(node, "name"):
            if node.name == "ruby":
                rb = node.find("rb")
                if rb is not None:
                    base = rb.get_text()
                else:
                    base = "".join(
                        c.get_text() if c.name else str(c) for c in node.children
                        if c.name not in ("rt", "rp")
                    )
                reading = "".join(rt.get_text() for rt in node.find_all("rt"))
                parts.append(f"{base}({reading})" if reading else base)
            else:
                parts.append(node.get_text())
        else:
            parts.append(str(node))
    return "".join(parts).strip()


def fetch_syosetu(c: httpx.Client, url: str, *, delay: float = 0.0) -> tuple[str, str]:
    validate_url(url)
    throttle(delay)
    soup = BeautifulSoup(_get(c, url), "html.parser")

    title_el = soup.find(class_=lambda c: c and "p-novel__title--rensai" in c.split())
    title = title_el.get_text(strip=True) if title_el else ""

    _skip = {"p-novel__text--preface", "p-novel__text--afterword"}
    content_els = soup.find_all(
        class_=lambda c: c and "js-novel-text" in c.split() and "p-novel__text" in c.split()
        and not (set(c.split()) & _skip)
    )
    if not content_els:
        raise ValueError("Could not find novel text on page")
    content = "\n".join(_para_text(p) for el in content_els for p in el.find_all("p"))

    return title, content


def _validate_series_url(url: str) -> None:
    validate_url(url)
    path = urlparse(url).path.rstrip("/")
    parts = [p for p in path.split("/") if p]
    if len(parts) != 1:
        raise ValueError(
            "URL must be a series root (e.g. https://novel18.syosetu.com/n7696mg/), "
            "not a chapter URL"
        )


_INDEX_NODES = (
    "div.p-eplist__chapter-title, div.p-eplist__sublist a, "
    "div.index_box div.chapter_title, dl.novel_sublist2 dd.subtitle a"
)


_JST = ZoneInfo("Asia/Tokyo")
_POSTED = re.compile(r"\d{4}/\d{1,2}/\d{1,2} \d{1,2}:\d{2}")


def _posted_at(anchor) -> datetime | None:
    """The chapter's post date (JST) from its index row, or None. A revision marker
    sits after the post date in the same cell, so the first match is the post date."""
    row = anchor.find_parent("div", class_="p-eplist__sublist")
    cell_selector = "div.p-eplist__update"
    if row is None:
        row = anchor.find_parent("dl", class_="novel_sublist2")
        cell_selector = "dt.long_update"
    cell = row.select_one(cell_selector) if row is not None else None
    match = _POSTED.search(cell.get_text(" ")) if cell is not None else None
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(), "%Y/%m/%d %H:%M").replace(tzinfo=_JST)
    except ValueError:
        return None


def latest_post(chapters: list[dict]) -> datetime | None:
    """The newest post date among the chapters, or None when none has one."""
    return max((ch["posted_at"] for ch in chapters if ch.get("posted_at")), default=None)


def _extract_chapters(
    soup: BeautifulSoup, base: str, group: str | None
) -> tuple[list[dict], str | None]:
    """Chapters in page order, each tagged with the chapter-title heading above it.
    ``group`` is the heading still open from the previous index page; the one open at
    the end of this page is returned for the next."""
    chapters = []
    for el in soup.select(_INDEX_NODES):  # document order
        if el.name != "a":
            group = el.get_text(strip=True) or None
            continue
        href = el.get("href", "")
        href_parts = [p for p in href.split("/") if p]
        try:
            num = int(href_parts[-1])
        except (ValueError, IndexError):
            continue
        title = el.get_text(strip=True)
        chapter_url = urljoin(base, href)
        chapters.append({"num": num, "title": title, "url": chapter_url, "group": group,
                         "posted_at": _posted_at(el)})
    return chapters, group


def _next_page_url(soup: BeautifulSoup, base: str) -> str | None:
    next_el = soup.select_one("a.c-pager__item.c-pager__item--next")
    if not next_el:
        return None
    href = next_el.get("href", "")
    return urljoin(base, href) if href else None


def _has_novel_text(soup: BeautifulSoup) -> bool:
    return soup.find(
        class_=lambda c: c and "js-novel-text" in c.split() and "p-novel__text" in c.split()
    ) is not None


def _novel_header(soup: BeautifulSoup) -> tuple[str, str]:
    title_el = soup.select_one("h1.p-novel__title") or soup.find(
        class_=lambda c: c and "p-novel__title" in c
    )
    title = title_el.get_text(strip=True) if title_el else ""
    author_el = soup.select_one("div.p-novel__author")
    author = ""
    if author_el:
        link = author_el.find("a")
        if link:
            author = link.get_text(strip=True)
        else:
            author = author_el.get_text(strip=True)
            for prefix in ("作者：", "作者:"):
                if author.startswith(prefix):
                    author = author[len(prefix):].strip()
                    break
    return title, author


def _walk_index(c: httpx.Client, url: str) -> tuple[BeautifulSoup, list[dict]]:
    """Every index page's chapters, sorted; also the root page's soup (fetched once)."""
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    current_url: str | None = url
    chapters: list[dict] = []
    group = None
    pages = 0
    root = None
    while current_url:
        if pages >= MAX_INDEX_PAGES:
            raise ScrapeError(f"the chapter list has more than {MAX_INDEX_PAGES} pages")
        pages += 1
        soup = BeautifulSoup(_get(c, current_url), "html.parser")
        root = root or soup
        found, group = _extract_chapters(soup, base, group)
        chapters.extend(found)
        current_url = _next_page_url(soup, base)
    chapters.sort(key=lambda ch: ch["num"])
    return root, chapters


def _short_story(soup: BeautifulSoup, url: str) -> list[dict]:
    title, _ = _novel_header(soup)
    return [{"num": 1, "title": title, "url": url, "group": None, "posted_at": None}]


def fetch_series_index(c: httpx.Client, url: str) -> list[dict]:
    _validate_series_url(url)
    root, chapters = _walk_index(c, url)
    if not chapters and _has_novel_text(root):
        return _short_story(root, url)
    return chapters


def read_novel(c: httpx.Client, url: str, *, delay: float = 0.0) -> dict:
    """Header and first index page of a series root; a short story is one chapter."""
    _validate_series_url(url)
    throttle(delay)
    base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    soup = BeautifulSoup(_get(c, url), "html.parser")
    title, author = _novel_header(soup)
    chapters, _ = _extract_chapters(soup, base, None)
    chapters.sort(key=lambda ch: ch["num"])
    if chapters:
        return {"title": title, "author": author, "short_story": False, "chapters": chapters}
    if _has_novel_text(soup):
        return {"title": title, "author": author, "short_story": True,
                "chapters": _short_story(soup, url)}
    raise NoChapters("no chapters found at this URL")
