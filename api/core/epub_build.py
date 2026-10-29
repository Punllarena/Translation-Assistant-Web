"""EPUB builder ported from the desktop ``translation_assistant/epub.py``: assembles an
EPUB3 zip in memory. The reader is in epub_read.py; the stylesheet, cover and title pages
are in epub_pages.py."""
import io
import re
import uuid
import zipfile
from datetime import UTC, datetime
from xml.sax.saxutils import escape

from api.core import epub_pages

_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _paragraph_to_html(text: str) -> str:
    """
    Escapes text for XML, converting **bold** markers to <b> tags.
    re.split with a capturing group returns alternating
    [plain, bold, plain, bold, ..., plain] -- odd indices are the matched
    bold runs.
    """
    parts = _BOLD_RE.split(text)
    escaped = []
    for i, part in enumerate(parts):
        piece = escape(part)
        escaped.append(f"<b>{piece}</b>" if i % 2 == 1 else piece)
    return "".join(escaped)


_CONTAINER_XML_OUT = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

_OPF_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="{lang}">
<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
<dc:title>{title}</dc:title>
<dc:language>{lang}</dc:language>
<dc:identifier id="uid">{identifier}</dc:identifier>
<meta property="dcterms:modified">{modified}</meta>
{credits}
{cover_meta}
</metadata>
<manifest>
{manifest}
</manifest>
<spine>
{spine}
</spine>
</package>
"""

_NAV_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">
<head><title>Table of Contents</title></head>
<body>
<nav epub:type="toc">
<ol>
{items}
</ol>
</nav>
{landmarks}
</body>
</html>
"""

_XHTML = "application/xhtml+xml"


def _credits(
    creator: str, illustrator: str, translator: str, publisher: str, source: str,
    description: str,
) -> str:
    """The OPF credit lines; a blank value emits nothing. Creators carry a role-refining
    <meta> (aut/ill), the shape open_book() reads them from; the translator is a
    dc:contributor with the trl role."""
    out = []
    for tag, ref, name, role in (
        ("dc:creator", "creator-aut", creator, "aut"),
        ("dc:creator", "creator-ill", illustrator, "ill"),
        ("dc:contributor", "contributor-trl", translator, "trl"),
    ):
        if name:
            out.append(f'<{tag} id="{ref}">{escape(name)}</{tag}>')
            out.append(f'<meta refines="#{ref}" property="role" scheme="marc:relators">{role}</meta>')
    if publisher:
        out.append(f"<dc:publisher>{escape(publisher)}</dc:publisher>")
    if source.strip():
        out.append(f"<dc:source>{escape(source)}</dc:source>")
    if description.strip():
        out.append(f"<dc:description>{escape(description)}</dc:description>")
    return "\n".join(out)


def build_epub(
    volume_title: str,
    chapters: list[tuple[str, list[tuple[str, str]], list[dict]]],
    *, language: str = "en",
    cover: dict | None = None,
    creator: str = "",
    illustrator: str = "",
    translator: str = "",
    publisher: str = "",
    identifier: str = "",
    source: str = "",
    description: str = "",
    modified: datetime | None = None,
) -> bytes:
    """
    chapters: [(chapter_title, content_items, chapter_images), ...] in output
    order. content_items is core.build_epub_content()'s return shape
    ([("text", paragraph) | ("image", src_path), ...]); chapter_images is
    [{"src_path": str, "data": bytes}, ...] -- the actual bytes to embed,
    keyed by the same src_path strings content_items references.
    cover: {"data": bytes, "media_type": str} or None. When present, the
    cover image gets a manifest item with properties="cover-image" plus a
    <meta name="cover" content="..."> entry for older-reader compatibility,
    and a cover page opens the book.
    creator/illustrator/translator/publisher/source/description: credits,
    see _credits(); each is omitted when blank, and all but description also
    go on the title page.
    identifier: dc:identifier text (e.g. an ISBN urn). When blank, a
    generated urn:uuid is used instead -- the OPF always needs *some* unique
    identifier. Callers pass a stable one: readers key reading position on it.
    modified: dcterms:modified (required by EPUB 3); now when None.

    The spine runs cover page, title page, chapters; every page links the
    stylesheet, and the nav document carries the landmarks. Images that are
    not EPUB core media types (JPEG, PNG, GIF, WebP, SVG) are left out, and so
    is a cover of another type.

    mimetype is stored uncompressed as the first entry (required by the EPUB
    spec so readers can identify the format without inflating the zip).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML_OUT)
        zf.writestr(f"OEBPS/{epub_pages.STYLESHEET_HREF}", epub_pages.STYLESHEET)

        manifest_items = [
            f'<item id="css" href="{epub_pages.STYLESHEET_HREF}" media-type="text/css"/>',
            f'<item id="title-page" href="text/title.xhtml" media-type="{_XHTML}"/>',
        ]
        spine_items = ['<itemref idref="title-page"/>']
        nav_lis = []
        image_id = 0
        used_image_hrefs: set[str] = set()  # zip-relative hrefs already claimed, across all chapters
        first_text_href = None

        zf.writestr("OEBPS/text/title.xhtml", epub_pages.title_page(
            volume_title, language, creator=creator, illustrator=illustrator,
            translator=translator, publisher=publisher, source=source,
        ))

        for i, (chapter_title, content_items, chapter_images) in enumerate(chapters, start=1):
            chap_id = f"chap{i}"
            href = f"text/chap{i}.xhtml"
            image_bytes_by_src = {img["src_path"]: img["data"] for img in chapter_images}
            written_images: dict[str, str] = {}  # src_path -> zip-relative href written this chapter

            # An image-only chapter (colour plate, frontispiece) gets no <h1>:
            # its "title" is a filename stub like "p-fmatter-003", and printing
            # that above a full-page illustration looks like a bug to a reader.
            has_text = any(kind == "text" for kind, _ in content_items)
            body_parts = []
            if has_text:
                first_text_href = first_text_href or href
                body_parts.append(f"<h1>{escape(chapter_title)}</h1>\n")
            for kind, value in content_items:
                if kind == "text":
                    body_parts.append(f"<p>{_paragraph_to_html(value)}</p>\n")
                    continue
                src_path = value
                if src_path not in written_images:
                    data = image_bytes_by_src.get(src_path)
                    media_type = epub_pages.image_type(src_path, data) if data is not None else None
                    if media_type is None:
                        continue  # no bytes, or not a type readers must show -- skip, not fatal
                    image_id += 1
                    # Keep the original name where possible (readable, round-trips
                    # predictably); number it only on a collision (two src_paths sharing
                    # a name, e.g. two chapters each with an "images/pic.png").
                    name = epub_pages.image_name(src_path, media_type)
                    img_href = f"images/{name}"
                    if img_href in used_image_hrefs:
                        img_href = f"images/{image_id}_{name}"
                    used_image_hrefs.add(img_href)
                    zf.writestr(f"OEBPS/{img_href}", data)
                    manifest_items.append(
                        f'<item id="img{image_id}" href="{img_href}" media-type="{media_type}"/>'
                    )
                    written_images[src_path] = img_href
                body_parts.append(
                    f'<p class="img"><img src="../{written_images[src_path]}" alt=""/></p>\n')

            section = ('<section epub:type="chapter" role="doc-chapter">' if has_text
                       else '<section class="plates">')
            zf.writestr(f"OEBPS/{href}", epub_pages.page(
                chapter_title, f"{section}\n{''.join(body_parts)}</section>\n", language,
            ))
            manifest_items.append(f'<item id="{chap_id}" href="{href}" media-type="{_XHTML}"/>')
            spine_items.append(f'<itemref idref="{chap_id}"/>')
            nav_lis.append(f'<li><a href="{href}">{escape(chapter_title)}</a></li>')

        cover_href = None
        cover_type = cover and epub_pages.image_type("", cover["data"], cover["media_type"])
        if cover_type:
            ext = epub_pages.EXT[cover_type]
            cover_href = f"images/cover{ext}"
            n = 0
            while cover_href in used_image_hrefs:
                n += 1
                cover_href = f"images/cover_{n}{ext}"
            used_image_hrefs.add(cover_href)
            zf.writestr(f"OEBPS/{cover_href}", cover["data"])
            manifest_items.append(
                f'<item id="cover-image" href="{cover_href}" '
                f'media-type="{cover_type}" properties="cover-image"/>'
            )
            zf.writestr("OEBPS/text/cover.xhtml", epub_pages.cover_page(cover_href, language))
            manifest_items.append(f'<item id="cover-page" href="text/cover.xhtml" media-type="{_XHTML}"/>')
            spine_items.insert(0, '<itemref idref="cover-page"/>')

        marks = [("cover", "text/cover.xhtml", "Cover")] if cover_href else []
        marks.append(("titlepage", "text/title.xhtml", "Title Page"))
        marks.append(("toc", "nav.xhtml", "Table of Contents"))
        if start := first_text_href or ("text/chap1.xhtml" if chapters else None):
            marks.append(("bodymatter", start, "Start"))
        zf.writestr("OEBPS/nav.xhtml", _NAV_TEMPLATE.format(
            lang=language, items="\n".join(nav_lis), landmarks=epub_pages.landmarks(marks),
        ))
        manifest_items.append(
            f'<item id="nav" href="nav.xhtml" media-type="{_XHTML}" properties="nav"/>'
        )

        stamp = (modified or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        opf = _OPF_TEMPLATE.format(
            title=escape(volume_title),
            lang=language,
            identifier=escape(identifier) if identifier else f"urn:uuid:{uuid.uuid4()}",
            modified=stamp,
            credits=_credits(creator, illustrator, translator, publisher, source, description),
            cover_meta='<meta name="cover" content="cover-image"/>' if cover_href else "",
            manifest="\n".join(manifest_items),
            spine="\n".join(spine_items),
        )
        zf.writestr("OEBPS/content.opf", opf)

    return buf.getvalue()
