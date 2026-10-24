"""What the EPUB reader sees inside a chapter file: its paragraph and illustration units,
TOC anchors, and inline text rendering (ruby, alt text, bold). Split out of epub_read.py."""
from bs4 import BeautifulSoup

from api.core.epub_runs import Piece, units


def anchors(xhtml: str, wanted: set[str]) -> list[str]:
    """The wanted ids that exist in the file, in document order."""
    if not wanted:
        return []
    tags = BeautifulSoup(xhtml, "html.parser").find_all(id=wanted)
    return list(dict.fromkeys(tag["id"] for tag in tags))


def count(pieces: tuple[Piece, ...], soup_of) -> tuple[int, int]:
    """(characters of paragraph text, illustrations) over a chapter's pieces."""
    chars = images = 0
    for piece in pieces:
        if (soup := soup_of(piece.href)) is None:
            continue
        for el in units(soup, piece.start, piece.end):
            if illustration_src(el):
                images += 1
            elif el.name == "p":
                chars += len(para_text(el))
    return chars, images


def illustration_src(el) -> str:
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


def para_text(p) -> str:
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
    return _render_inline(node.children)


def _render_inline(nodes) -> str:
    parts = []
    for child in nodes:
        if not hasattr(child, "name") or child.name is None:
            parts.append(str(child))
            continue
        if child.name == "ruby":
            rb = child.find("rb")
            if rb is not None:
                base = _extract_inline(rb)
            else:
                # Rendered, not str(): Kobo wraps base characters in koboSpan tags.
                base = _render_inline(
                    c for c in child.children
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
