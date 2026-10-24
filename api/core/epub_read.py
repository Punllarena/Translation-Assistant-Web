"""EPUB reader ported from the desktop ``translation_assistant/epub.py``; the builder is
in epub_build.py. Zip/XML handling only via stdlib zipfile + the already-installed
beautifulsoup4. Archive-safety checks and limits are ours, in epub_safety.py.

Departure from the desktop: chapters are cut at table-of-contents anchors (epub_runs.py),
not one per file, so a chapter can start mid-file and run across several files, and
off-TOC pages continue the chapter before them."""
import posixpath
import warnings
import zipfile
from collections.abc import Sequence
from pathlib import Path
from typing import IO
from urllib.parse import unquote

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from api.core.epub_runs import Piece, plan_chapters, units
from api.core.epub_safety import (
    EpubError,
    TextBudgetExceeded,
    charge,
    check_archive,
    read_text,
    unreadable,
)
from api.core.epub_units import anchors, count, illustration_src, para_text
from api.core.text import build_new_file, parse_file_content

# OPF/NCX are XML parsed with html.parser on purpose (as the desktop does).
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

__all__ = ["EpubError", "extract_chapter_content", "open_book"]


def _resolve(base_dir: str, href: str) -> str:
    """Resolve an href (may carry a #fragment) against base_dir, inside the zip."""
    href = href.split("#", 1)[0]
    return posixpath.normpath(posixpath.join(base_dir, href))


def _spine(opf: BeautifulSoup, opf_dir: str) -> list[str]:
    """Reading order: the spine's zip paths, minus the nav document and repeats."""
    nav_ids = {
        item.get("id")
        for item in opf.find_all("item", attrs={"properties": lambda v: v and "nav" in v.split()})
    }
    href_by_id = {
        item["id"]: _resolve(opf_dir, item["href"])
        for item in opf.find_all("item")
        if item.get("id") and item.get("href")
    }
    spine = opf.find("spine")
    hrefs: list[str] = []
    for ref in spine.find_all("itemref") if spine is not None else []:
        idref = ref.get("idref", "")
        href = href_by_id.get(idref)
        if idref not in nav_ids and href is not None and href not in hrefs:
            hrefs.append(href)
    return hrefs


def _find_cover_href(opf: BeautifulSoup, opf_dir: str) -> str | None:
    """EPUB3: manifest item with properties="cover-image".
    EPUB2 fallback: <meta name="cover" content="ID"> + manifest item with that id."""
    cover_item = opf.find("item", attrs={"properties": lambda v: v and "cover-image" in v.split()})
    if cover_item is not None:
        return _resolve(opf_dir, cover_item["href"])

    cover_meta = opf.find("meta", attrs={"name": "cover"})
    if cover_meta is not None and cover_meta.get("content"):
        item = opf.find("item", attrs={"id": cover_meta["content"]})
        if item is not None:
            return _resolve(opf_dir, item["href"])

    return None


def _find_metadata(opf: BeautifulSoup) -> dict:
    """
    Extracts author/illustrator (from dc:creator + role-refining <meta>),
    publisher, and identifier from the OPF's <metadata> block.

    bs4's html.parser treats <meta> as an HTML void element, so
    <meta refines="#creator01" property="role" ...>aut</meta> parses with
    "aut" as the meta tag's *next sibling text node*, not its content --
    meta.get_text() would return "". Read the role via next_sibling instead.
    NavigableString objects have a .name attribute equal to None, so the
    "is this a tag" check must be `getattr(node, "name", None) is None`,
    not a bare hasattr check (which is True for text nodes too).
    """
    role_by_id: dict[str, str] = {}
    for meta in opf.find_all("meta", attrs={"property": "role"}):
        refines = meta.get("refines", "")
        if not refines.startswith("#"):
            continue
        sib = meta.next_sibling
        if sib is not None and getattr(sib, "name", None) is None:
            role_by_id[refines[1:]] = str(sib).strip()

    authors = []
    illustrators = []
    for creator in opf.find_all("dc:creator"):
        role = role_by_id.get(creator.get("id", ""), "aut")
        name = creator.get_text(strip=True)
        (illustrators if role == "ill" else authors).append(name)

    publisher_el = opf.find("dc:publisher")
    identifier_el = opf.find("dc:identifier")
    return {
        "author": ", ".join(authors),
        "illustrator": ", ".join(illustrators),
        "publisher": publisher_el.get_text(strip=True) if publisher_el else "",
        "identifier": identifier_el.get_text(strip=True) if identifier_el else "",
    }


def open_book(source: str | Path | IO[bytes]) -> dict:
    """
    Returns {"title": str, "chapters": [{"order", "title", "href", "char_count",
    "image_count", "image_only", "pieces"}, ...], "cover_href", ...metadata} in reading
    order. href is the chapter's key (zip path, plus "#fragment" when it starts at a TOC
    anchor); pieces are what extract_chapter_content() reads. Chapters with neither text
    nor images are dropped and the rest numbered 1..N.

    Raises EpubError if the file isn't a zip / has no OPF / has neither an
    EPUB3 nav doc nor an EPUB2 toc.ncx.
    """
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise EpubError("Not a valid EPUB (bad zip)") from exc

    parsed = [0]  # XML/XHTML bytes read so far, against MAX_PARSED_TEXT
    with unreadable(), zf:
        check_archive(zf)
        container = BeautifulSoup(read_text(zf, "META-INF/container.xml", parsed), "html.parser")
        rootfile = container.find("rootfile")
        if rootfile is None or not rootfile.get("full-path"):
            raise EpubError("container.xml has no rootfile")
        opf_path = rootfile["full-path"]
        opf_dir = posixpath.dirname(opf_path)

        opf = BeautifulSoup(read_text(zf, opf_path, parsed), "html.parser")
        title_el = opf.find("dc:title")
        title = title_el.get_text(strip=True) if title_el else ""

        toc = _read_toc(zf, opf, opf_dir, parsed)
        cover_href = _find_cover_href(opf, opf_dir)
        metadata = _find_metadata(opf)

        texts: dict[str, str | None] = {}  # each file read (and charged) once

        def text_of(href: str) -> str | None:
            if href not in texts:
                try:
                    texts[href] = read_text(zf, href, parsed)
                except TextBudgetExceeded:
                    raise
                except EpubError:
                    texts[href] = None  # broken entry: counts nothing, so it is dropped
            return texts[href]

        last: dict[str, BeautifulSoup | None] = {}  # chapters run in spine order

        def soup_of(href: str) -> BeautifulSoup | None:
            if href not in last:
                xhtml = text_of(href)
                last.clear()
                last[href] = BeautifulSoup(xhtml, "html.parser") if xhtml else None
            return last[href]

        spine = [href for href in _spine(opf, opf_dir) if text_of(href) is not None]
        found = {
            href: anchors(texts[href], {f for _, h, f in toc if h == href and f is not None})
            for href in spine
        }
        chapters = []
        for planned in plan_chapters(spine, toc, found):
            char_count, image_count = count(planned.pieces, soup_of)
            if not (char_count or image_count):
                continue
            chapters.append({
                "order": len(chapters) + 1, "title": planned.title, "href": planned.key,
                "char_count": char_count, "image_count": image_count,
                "image_only": image_count > 0 and char_count == 0, "pieces": planned.pieces,
            })

        return {"title": title, "chapters": chapters, "cover_href": cover_href, **metadata}


def extract_chapter_content(
    source: str | Path | IO[bytes], href: str | Sequence[Piece],
    budget: list[int] | None = None, soups: dict[str, BeautifulSoup] | None = None,
) -> tuple[str, list[dict]]:
    """
    Returns (text, images) for one chapter: a plain href is the whole file, otherwise
    the pieces open_book() planned, read in order.
    text: joined-paragraph string, ready for core.build_new_file().
    images: [{"anchor_position": int, "src_path": str, "data": bytes}, ...]
    in chapter order. Does not include the cover -- that comes from
    open_book()'s cover_href, read separately.

    anchor_position indexes into the *final* raw_lines array. Since
    build_new_file() splits each paragraph into multiple %/$ sentence lines,
    "between source paragraph 3 and 4" isn't the same offset as "between
    raw_lines[3] and raw_lines[4]" once paragraph 3 has split into two
    sentences. Resolved by running each individual paragraph alone through
    build_new_file()+parse_file_content() as a throwaway counting pass and
    accumulating a running raw-line offset -- this never feeds the actual
    output, only the count, since build_new_file()'s sentence-splitting is
    local per input line.

    budget (remaining bytes, mutated in place) is charged each image reference's
    size before anything is read (EpubBudgetExceeded when it would go negative); each
    distinct image is read once and repeated references share its bytes.

    soups (zip path -> parsed file, filled in place) lets one import parse a file holding
    several chapters once; pass the same dict only with the same source.
    """
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise EpubError("Not a valid EPUB (bad zip)") from exc

    with unreadable(), zf:
        check_archive(zf)
        pieces = (Piece(href, None, None),) if isinstance(href, str) else tuple(href)
        text_paragraphs: list[str] = []
        images: list[dict] = []
        read_once: dict[str, bytes] = {}
        offset = 0  # keeps counting across pieces
        for piece in pieces:
            soup = soups.get(piece.href) if soups is not None else None
            if soup is None:
                soup = BeautifulSoup(read_text(zf, piece.href), "html.parser")
                if soups is not None:
                    soups[piece.href] = soup
            base_dir = posixpath.dirname(piece.href)
            for el in units(soup, piece.start, piece.end):
                src = illustration_src(el)
                if src:
                    resolved_src = _resolve(base_dir, src)
                    data = read_once.get(resolved_src)
                    if data is None:
                        try:
                            size = zf.getinfo(resolved_src).file_size
                        except KeyError:
                            continue  # broken manifest reference -- skip, not fatal
                        charge(budget, size)
                        data = read_once[resolved_src] = zf.read(resolved_src)
                    else:
                        charge(budget, len(data))
                    images.append({
                        "anchor_position": offset, "src_path": resolved_src, "data": data,
                    })
                    continue
                if el.name == "image":
                    continue

                paragraph = para_text(el)
                if not paragraph:
                    continue
                text_paragraphs.append(paragraph)
                para_raw_lines, _, _ = parse_file_content(build_new_file(paragraph))
                offset += len(para_raw_lines)

    return "\n".join(text_paragraphs), images


def _toc_entry(title: str, base_dir: str, href: str) -> tuple[str, str, str | None]:
    return title, _resolve(base_dir, href), unquote(href.partition("#")[2]) or None


def _read_toc(
    zf: zipfile.ZipFile, opf: BeautifulSoup, opf_dir: str, parsed: list[int],
) -> list[tuple[str, str, str | None]]:
    """Returns [(chapter_title, resolved_href, fragment or None), ...] in TOC order."""
    nav_item = opf.find("item", attrs={"properties": lambda v: v and "nav" in v.split()})
    if nav_item is not None:
        nav_href = _resolve(opf_dir, nav_item["href"])
        nav_soup = BeautifulSoup(read_text(zf, nav_href, parsed), "html.parser")
        nav_dir = posixpath.dirname(nav_href)
        # An EPUB3 nav doc may hold several <nav>s (toc / landmarks / page-list)
        # in any order, so prefer the toc-typed one. html.parser keeps the
        # colon in "epub:type" verbatim (same reason dc:title works above).
        # Fall back to the first <nav> for EPUB2-ish files that omit the attr.
        toc_nav = (
            nav_soup.find("nav", attrs={"epub:type": lambda v: v and "toc" in v.split()})
            or nav_soup.find("nav")
        )
        if toc_nav is None:
            raise EpubError("EPUB3 nav document has no <nav> element")
        return [
            _toc_entry(a.get_text(strip=True), nav_dir, a["href"])
            for a in toc_nav.find_all("a") if a.get("href")
        ]

    ncx_item = next(
        (item for item in opf.find_all("item")
         if item.get("media-type") == "application/x-dtbncx+xml"),
        None,
    )
    if ncx_item is None:
        raise EpubError("No EPUB3 nav doc and no EPUB2 toc.ncx found")
    ncx_href = _resolve(opf_dir, ncx_item["href"])
    ncx_soup = BeautifulSoup(read_text(zf, ncx_href, parsed), "html.parser")
    ncx_dir = posixpath.dirname(ncx_href)
    entries = []
    for navpoint in ncx_soup.find_all("navpoint"):
        content_el = navpoint.find("content")
        if content_el is None or not content_el.get("src"):
            continue
        label_el = navpoint.find("text")
        title = label_el.get_text(strip=True) if label_el else ""
        entries.append(_toc_entry(title, ncx_dir, content_el["src"]))
    return entries
