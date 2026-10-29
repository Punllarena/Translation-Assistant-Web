"""The fixed parts of an exported EPUB: the stylesheet, the cover and title pages, the
landmarks, and the image rules (core media types, safe file names). epub_build.py puts
them together."""
import posixpath
import re
from xml.sax.saxutils import escape

STYLESHEET_HREF = "styles/book.css"

# Book typesetting: indented paragraphs with no gap, centred images that fit the screen.
# No font family, size or colour, so the reader's own settings still win.
STYLESHEET = """body { margin: 0; padding: 0; }
h1 { font-size: 1.4em; text-align: center; margin: 1.5em 0;
     page-break-after: avoid; break-after: avoid; }
p { margin: 0; text-indent: 1.5em; orphans: 2; widows: 2; }
h1 + p, p.img + p { text-indent: 0; }
p.img { text-indent: 0; text-align: center; margin: 1em 0;
        page-break-inside: avoid; break-inside: avoid; }
img { max-width: 100%; height: auto; }
.plates p.img { margin: 0; page-break-after: always; break-after: page; }
.cover { margin: 0; padding: 0; text-align: center; }
.cover img { max-height: 100vh; }
.titlepage { text-align: center; margin-top: 20%; }
.titlepage h1 { font-size: 1.8em; margin: 0 0 1.5em; }
.titlepage p { text-indent: 0; margin: 0.6em 0; }
"""

# EPUB 3 core media types; anything else would need a fallback, so it is left out.
EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
        "image/webp": ".webp", "image/svg+xml": ".svg"}
_BY_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
           ".gif": "image/gif", ".webp": "image/webp", ".svg": "image/svg+xml"}
_UNSAFE = re.compile(r"[^A-Za-z0-9_-]+")


def image_type(name: str, data: bytes, declared: str | None = None) -> str | None:
    """The image's core media type, read from its bytes first (an imported file can be
    misnamed), then the declared type, then the name; None when it is none of them."""
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"GIF8"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if declared in EXT:
        return declared
    return _BY_EXT.get(posixpath.splitext(name)[1].lower())


def image_name(src_path: str, media_type: str) -> str:
    """A file name readers and epubcheck accept: ASCII letters, digits, _ and -, and the
    extension of its media type, so the href needs no escaping."""
    stem = _UNSAFE.sub("_", posixpath.splitext(posixpath.basename(src_path))[0]).strip("_")
    return f"{stem or 'image'}{EXT[media_type]}"


_PAGE = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops"
      xml:lang="{lang}" lang="{lang}">
<head><title>{title}</title><link rel="stylesheet" type="text/css" href="../{css}"/></head>
<body>
{body}</body>
</html>
"""


def page(title: str, body: str, lang: str) -> str:
    """One XHTML page in text/, linked to the stylesheet; title is escaped here."""
    return _PAGE.format(title=escape(title), body=body, lang=lang, css=STYLESHEET_HREF)


def cover_page(image_href: str, lang: str) -> str:
    return page("Cover", (
        '<section epub:type="cover" class="cover">\n'
        f'<img src="../{image_href}" alt="Cover"/>\n</section>\n'
    ), lang)


def title_page(
    title: str, lang: str, *, creator: str, illustrator: str, translator: str,
    publisher: str, source: str,
) -> str:
    """The title and credits; epub_read skips it on import (text-only titlepage)."""
    lines = [
        ("by", creator), ("Illustrated by", illustrator), ("Translated by", translator),
        ("Original work:", source.strip()), ("", publisher),
    ]
    credits = "".join(
        f'<p>{escape(f"{label} {name}".strip())}</p>\n' for label, name in lines if name
    )
    return page(title, (
        '<section epub:type="titlepage" class="titlepage">\n'
        f"<h1>{escape(title)}</h1>\n{credits}</section>\n"
    ), lang)


def landmarks(entries: list[tuple[str, str, str]]) -> str:
    """The nav document's landmarks list from (epub:type, href, label)."""
    items = "\n".join(
        f'<li><a epub:type="{kind}" href="{href}">{escape(label)}</a></li>'
        for kind, href, label in entries
    )
    return f'<nav epub:type="landmarks" hidden="">\n<ol>\n{items}\n</ol>\n</nav>'
