"""EPUB reader ported from the desktop ``translation_assistant/epub.py``; the builder is
in epub_build.py. Zip/XML handling only via stdlib zipfile + the already-installed
beautifulsoup4. Archive-safety checks (``_check_archive``) are ours (spec section 6)."""
import posixpath
import warnings
import zipfile
import zlib
from contextlib import contextmanager
from pathlib import Path
from typing import IO

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from api.core.text import build_new_file, parse_file_content

# OPF/NCX are XML parsed with html.parser on purpose (as the desktop does).
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

MAX_UNCOMPRESSED = 256 * 1024 * 1024  # ours (spec §6): cap what a book may expand to


class EpubError(ValueError):
    """Raised when an EPUB file can't be parsed."""


def _check_archive(zf: zipfile.ZipFile) -> None:
    """Refuse absolute and parent-relative entry names and oversized archives
    (spec §6). Entries are only ever read by name, never extracted to disk, but a
    book that names one is not one we should trust with anything else."""
    total = 0
    for info in zf.infolist():
        parts = info.filename.replace("\\", "/").split("/")
        if info.filename.startswith(("/", "\\")) or ".." in parts:
            raise EpubError(f"unsafe path in EPUB: {info.filename!r}")
        total += info.file_size
        if total > MAX_UNCOMPRESSED:
            raise EpubError(f"EPUB expands to more than {MAX_UNCOMPRESSED // (1024 * 1024)} MB")


@contextmanager
def _unreadable():
    """Hostile but valid zips fail in many ways below EpubError (bad encoding, a corrupt
    deflate stream, an encrypted entry, a manifest item without href); callers only ever
    handle EpubError."""
    try:
        yield
    except (KeyError, UnicodeDecodeError, zlib.error, RuntimeError, NotImplementedError,
            EOFError, zipfile.BadZipFile) as exc:
        raise EpubError(f"Not a readable EPUB: {type(exc).__name__}") from exc


def _read(zf: zipfile.ZipFile, path: str) -> str:
    try:
        return zf.read(path).decode("utf-8")
    except KeyError as exc:
        raise EpubError(f"Missing file in EPUB: {path}") from exc


def _resolve(base_dir: str, href: str) -> str:
    """Resolve an href (may carry a #fragment) against base_dir, inside the zip."""
    href = href.split("#", 1)[0]
    return posixpath.normpath(posixpath.join(base_dir, href))


def _dedupe_by_href(entries: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """
    Keep the first entry per resolved href.

    A nested TOC (Part -> Section#fragment) flattens to several entries that
    all resolve to the same file once the #fragment is stripped. Since
    extract_chapter_content() extracts the WHOLE file, keeping all of them would
    create N documents each holding the entire file's text. One document per
    unique file is the correct degradation for a whole-file text extractor.
    """
    seen = set()
    result = []
    for title, href in entries:
        if href in seen:
            continue
        seen.add(href)
        result.append((title, href))
    return result


def _order_by_spine(
    opf: BeautifulSoup, opf_dir: str, toc_entries: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """
    Reading order comes from the spine, titles from the TOC.

    The TOC is only a navigation subset: image-only front/back matter (colour
    plates, frontispiece, character sheet, afterword art) is routinely left out
    of it, so listing TOC entries alone silently drops those pages and every
    illustration on them. Pages the spine doesn't reference are appended at the
    end so a TOC-only-but-off-spine entry still survives.
    """
    title_by_href = {href: title for title, href in toc_entries}
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
    ordered: list[tuple[str, str]] = []
    seen: set[str] = set()
    for ref in spine.find_all("itemref") if spine is not None else []:
        idref = ref.get("idref", "")
        if idref in nav_ids:
            continue
        href = href_by_id.get(idref)
        if href is None or href in seen:
            continue
        seen.add(href)
        # Off-TOC pages have no title of their own (their <title> is usually the
        # book title, repeated on every page), so name them after the file.
        fallback = posixpath.splitext(posixpath.basename(href))[0]
        ordered.append((title_by_href.get(href) or fallback, href))
    ordered.extend((title, href) for title, href in toc_entries if href not in seen)
    return ordered


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
    Returns {"title": str, "chapters": [{"order": int, "title": str,
    "href": str, "char_count": int}, ...]} in TOC order. hrefs are resolved
    to full zip-internal paths.

    Raises EpubError if the file isn't a zip / has no OPF / has neither an
    EPUB3 nav doc nor an EPUB2 toc.ncx.
    """
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise EpubError("Not a valid EPUB (bad zip)") from exc

    with _unreadable(), zf:
        _check_archive(zf)
        container = BeautifulSoup(_read(zf, "META-INF/container.xml"), "html.parser")
        rootfile = container.find("rootfile")
        if rootfile is None or not rootfile.get("full-path"):
            raise EpubError("container.xml has no rootfile")
        opf_path = rootfile["full-path"]
        opf_dir = posixpath.dirname(opf_path)

        opf = BeautifulSoup(_read(zf, opf_path), "html.parser")
        title_el = opf.find("dc:title")
        title = title_el.get_text(strip=True) if title_el else ""

        toc_entries = _dedupe_by_href(_read_toc(zf, opf, opf_dir))
        entries = _order_by_spine(opf, opf_dir, toc_entries)
        cover_href = _find_cover_href(opf, opf_dir)
        metadata = _find_metadata(opf)

        chapters = []
        for order, (chap_title, href) in enumerate(entries, start=1):
            try:
                xhtml = _read(zf, href)
            except EpubError:
                continue  # broken TOC entry — skip rather than fail the whole import
            soup = BeautifulSoup(xhtml, "html.parser")
            char_count = len(soup.get_text().strip())
            image_count = sum(1 for el in soup.find_all(["p", "image"]) if _illustration_src(el))
            chapters.append({
                "order": order, "title": chap_title, "href": href,
                "char_count": char_count, "image_count": image_count,
            })

        return {"title": title, "chapters": chapters, "cover_href": cover_href, **metadata}


def extract_chapter_content(
    source: str | Path | IO[bytes], href: str,
) -> tuple[str, list[dict]]:
    """
    Returns (text, images).
    text: joined-paragraph string, ready
    for core.build_new_file().
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
    """
    try:
        zf = zipfile.ZipFile(source)
    except zipfile.BadZipFile as exc:
        raise EpubError("Not a valid EPUB (bad zip)") from exc

    with _unreadable(), zf:
        _check_archive(zf)
        xhtml = _read(zf, href)
        soup = BeautifulSoup(xhtml, "html.parser")

        text_paragraphs: list[str] = []
        images: list[dict] = []
        offset = 0
        base_dir = posixpath.dirname(href)

        for el in soup.find_all(["p", "image"]):
            src = _illustration_src(el)
            if src:
                resolved_src = _resolve(base_dir, src)
                try:
                    data = zf.read(resolved_src)
                except KeyError:
                    continue  # broken manifest reference -- skip, not fatal
                images.append({
                    "anchor_position": offset, "src_path": resolved_src, "data": data,
                })
                continue
            if el.name == "image":
                continue

            para_text = _para_text(el)
            if not para_text:
                continue
            text_paragraphs.append(para_text)
            para_raw_lines, _, _ = parse_file_content(build_new_file(para_text))
            offset += len(para_raw_lines)

    return "\n".join(text_paragraphs), images


def _illustration_src(el) -> str:
    """
    The image source of a standalone illustration, or "" if el isn't one.

    Two shapes in the wild: a reflowable <p><img src=".."/></p>, and the
    fixed-layout <svg><image xlink:href=".."/></svg> that Japanese publishers
    use for full-page colour plates. SVG2 allows a plain href, so accept both.
    """
    if el.name == "image":
        return el.get("xlink:href") or el.get("href") or ""
    if _is_standalone_illustration(el):
        img = el.find("img")
        return img.get("src", "") if img is not None else ""
    return ""


def _is_standalone_illustration(p) -> bool:
    """True if a <p>'s only meaningful child is a single <img>."""
    children = [c for c in p.children if not (isinstance(c, str) and not c.strip())]
    return len(children) == 1 and getattr(children[0], "name", None) == "img"


def _para_text(p) -> str:
    if _is_standalone_illustration(p):
        return ""
    return _extract_inline(p).strip()


def _extract_inline(node) -> str:
    """
    Recursively render a tag's text content:
      - <ruby>base<rt>reading</rt></ruby> -> "base(reading)"
      - <img alt="..."> -> alt text
      - class="bold" -> "**...**" (inline text convention, same approach as
        ruby -- the translator sees the markers and may wrap the matching
        English substring the same way if they want bold to survive export)
      - everything else recurses into children (so ruby/gaiji/bold still
        resolve when nested inside further tags).
    """
    parts = []
    for child in node.children:
        if not hasattr(child, "name") or child.name is None:
            parts.append(str(child))
            continue
        if child.name == "ruby":
            rb = child.find("rb")
            if rb is not None:
                base = rb.get_text()
            else:
                base = "".join(
                    str(c) for c in child.children
                    if not (hasattr(c, "name") and c.name in ("rt", "rp"))
                )
            reading = "".join(rt.get_text() for rt in child.find_all("rt"))
            parts.append(f"{base}({reading})" if reading else base)
        elif child.name == "img":
            alt = child.get("alt", "")
            if alt:
                parts.append(alt)
        elif "bold" in (child.get("class") or []):
            parts.append(f"**{_extract_inline(child)}**")
        else:
            parts.append(_extract_inline(child))
    return "".join(parts)


def _read_toc(zf: zipfile.ZipFile, opf: BeautifulSoup, opf_dir: str) -> list[tuple[str, str]]:
    """Returns [(chapter_title, resolved_href), ...] in TOC order."""
    nav_item = opf.find("item", attrs={"properties": lambda v: v and "nav" in v.split()})
    if nav_item is not None:
        nav_href = _resolve(opf_dir, nav_item["href"])
        nav_soup = BeautifulSoup(_read(zf, nav_href), "html.parser")
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
            (a.get_text(strip=True), _resolve(nav_dir, a["href"]))
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
    ncx_soup = BeautifulSoup(_read(zf, ncx_href), "html.parser")
    ncx_dir = posixpath.dirname(ncx_href)
    entries = []
    for navpoint in ncx_soup.find_all("navpoint"):
        content_el = navpoint.find("content")
        if content_el is None or not content_el.get("src"):
            continue
        label_el = navpoint.find("text")
        title = label_el.get_text(strip=True) if label_el else ""
        entries.append((title, _resolve(ncx_dir, content_el["src"])))
    return entries
