"""Syosetu fetching, from the desktop translation_assistant/scraper.py: URL checks and
the fetch_* functions. The QThread workers are gone (the jobs worker replaces them).
HTTP goes through an injected httpx.Client so tests replay recorded HTML (spec §12)."""

import threading
import time
from urllib.parse import urljoin, urlparse

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
                        str(c) for c in node.children
                        if not (hasattr(c, "name") and c.name in ("rt", "rp"))
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


def _extract_chapters(soup: BeautifulSoup, base: str) -> list[dict]:
    links = soup.select("div.p-eplist__sublist a") or [
        dd.find("a") for dd in soup.select("dl.novel_sublist2 dd.subtitle")
    ]
    chapters = []
    for a in links:
        if not a:
            continue
        href = a.get("href", "")
        href_parts = [p for p in href.split("/") if p]
        try:
            num = int(href_parts[-1])
        except (ValueError, IndexError):
            continue
        title = a.get_text(strip=True)
        chapter_url = urljoin(base, href)
        chapters.append({"num": num, "title": title, "url": chapter_url})
    return chapters


def _next_page_url(soup: BeautifulSoup, base: str) -> str | None:
    next_el = soup.select_one("a.c-pager__item.c-pager__item--next")
    if not next_el:
        return None
    href = next_el.get("href", "")
    return urljoin(base, href) if href else None


def fetch_series_index(c: httpx.Client, url: str) -> list[dict]:
    _validate_series_url(url)
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    current_url: str | None = url
    chapters = []
    pages = 0
    while current_url:
        if pages >= MAX_INDEX_PAGES:
            raise ScrapeError(f"the chapter list has more than {MAX_INDEX_PAGES} pages")
        pages += 1
        soup = BeautifulSoup(_get(c, current_url), "html.parser")
        chapters.extend(_extract_chapters(soup, base))
        current_url = _next_page_url(soup, base)
    chapters.sort(key=lambda ch: ch["num"])
    return chapters
