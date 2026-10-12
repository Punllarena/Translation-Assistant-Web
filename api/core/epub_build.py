"""EPUB builder ported from the desktop ``translation_assistant/epub.py``: assembles a
minimal valid EPUB3 zip in memory. The reader is in epub_read.py."""
import io
import mimetypes
import posixpath
import re
import zipfile
from xml.sax.saxutils import escape


def _escape_attr(s: str) -> str:
    """Escape a string for safe use inside a double-quoted XML attribute.

    xml.sax.saxutils.escape() only escapes &, <, > -- not " -- so it is
    insufficient on its own for attribute values (as opposed to text nodes).
    """
    return escape(s, {'"': "&quot;"})


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
{creator_entries}
{publisher_entry}
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
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}">
<head><title>Table of Contents</title></head>
<body>
<nav epub:type="toc">
<ol>
{items}
</ol>
</nav>
</body>
</html>
"""

_CHAPTER_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="{lang}">
<head><title>{title}</title></head>
<body>
{body}</body>
</html>
"""


def build_epub(
    volume_title: str,
    chapters: list[tuple[str, list[tuple[str, str]], list[dict]]],
    *, language: str = "en",
    cover: dict | None = None,
    creator: str = "",
    illustrator: str = "",
    publisher: str = "",
    identifier: str = "",
) -> bytes:
    """
    chapters: [(chapter_title, content_items, chapter_images), ...] in output
    order. content_items is core.build_epub_content()'s return shape
    ([("text", paragraph) | ("image", src_path), ...]); chapter_images is
    [{"src_path": str, "data": bytes}, ...] -- the actual bytes to embed,
    keyed by the same src_path strings content_items references.
    cover: {"data": bytes, "media_type": str} or None. When present, the
    cover image gets a manifest item with properties="cover-image" plus a
    <meta name="cover" content="..."> entry for older-reader compatibility.
    creator/illustrator: author/illustrator names. When either is given, a
    dc:creator entry is emitted with a role-refining <meta> (aut/ill),
    matching the shape open_book() reads them from. Blank means omitted.
    publisher: dc:publisher text, omitted when blank.
    identifier: dc:identifier text (e.g. an ISBN urn). When blank, a
    generated urn:uuid is used instead -- unlike creator/publisher, the OPF
    always needs *some* unique identifier, so this one is never omitted,
    only ever substituted.

    Assembles a minimal valid EPUB3 zip in memory using stdlib zipfile +
    xml.sax.saxutils.escape — no new dependency. mimetype is stored
    uncompressed as the first entry (required by the EPUB spec so readers
    can identify the format without inflating the zip).

    ponytail: no stylesheet is generated -- reader default styling only.
    ponytail: no dedicated cover.xhtml title page -- the manifest/meta cover
    metadata alone is enough for the readers that matter; add a real cover
    page later only if a specific reader needs one.
    """
    import uuid

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        zf.writestr("META-INF/container.xml", _CONTAINER_XML_OUT)

        manifest_items = []
        spine_items = []
        nav_lis = []
        image_id = 0
        used_image_hrefs: set[str] = set()  # zip-relative hrefs already claimed, across all chapters

        for i, (chapter_title, content_items, chapter_images) in enumerate(chapters, start=1):
            chap_id = f"chap{i}"
            href = f"text/chap{i}.xhtml"
            image_bytes_by_src = {img["src_path"]: img["data"] for img in chapter_images}
            written_images: dict[str, str] = {}  # src_path -> zip-relative href written this chapter

            # An image-only chapter (colour plate, frontispiece) gets no <h1>:
            # its "title" is a filename stub like "p-fmatter-003", and printing
            # that above a full-page illustration looks like a bug to a reader.
            body_parts = []
            if any(kind == "text" for kind, _ in content_items):
                body_parts.append(f"<h1>{escape(chapter_title)}</h1>\n")
            for kind, value in content_items:
                if kind == "text":
                    body_parts.append(f"<p>{_paragraph_to_html(value)}</p>\n")
                else:
                    src_path = value
                    if src_path not in written_images:
                        image_id += 1
                        data = image_bytes_by_src.get(src_path)
                        if data is None:
                            continue  # referenced image has no bytes -- skip, not fatal
                        # Preserve the original basename where possible (readable,
                        # round-trips predictably); fall back to a numbered prefix
                        # only on a collision (two different src_paths sharing a
                        # basename, e.g. two chapters each with an "images/pic.png").
                        basename = posixpath.basename(src_path) or f"{image_id}.img"
                        img_href = f"images/{basename}"
                        if img_href in used_image_hrefs:
                            img_href = f"images/{image_id}_{basename}"
                        used_image_hrefs.add(img_href)
                        zf.writestr(f"OEBPS/{img_href}", data)
                        media_type = mimetypes.guess_type(src_path)[0] or "application/octet-stream"
                        manifest_items.append(
                            f'<item id="img{image_id}" href="{_escape_attr(img_href)}" '
                            f'media-type="{_escape_attr(media_type)}"/>'
                        )
                        written_images[src_path] = img_href
                    body_parts.append(f'<p><img src="../{written_images[src_path]}"/></p>\n')

            xhtml = _CHAPTER_TEMPLATE.format(
                title=escape(chapter_title), body="".join(body_parts), lang=language,
            )
            zf.writestr(f"OEBPS/{href}", xhtml)
            manifest_items.append(
                f'<item id="{chap_id}" href="{href}" media-type="application/xhtml+xml"/>'
            )
            spine_items.append(f'<itemref idref="{chap_id}"/>')
            nav_lis.append(f'<li><a href="{href}">{escape(chapter_title)}</a></li>')

        zf.writestr("OEBPS/nav.xhtml", _NAV_TEMPLATE.format(lang=language, items="\n".join(nav_lis)))
        manifest_items.append(
            '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>'
        )

        cover_meta = ""
        if cover is not None:
            ext = mimetypes.guess_extension(cover["media_type"]) or ".img"
            cover_href = f"images/cover{ext}"
            if cover_href in used_image_hrefs:
                n = 1
                while f"images/cover_{n}{ext}" in used_image_hrefs:
                    n += 1
                cover_href = f"images/cover_{n}{ext}"
            used_image_hrefs.add(cover_href)
            zf.writestr(f"OEBPS/{cover_href}", cover["data"])
            manifest_items.append(
                f'<item id="cover-image" href="{_escape_attr(cover_href)}" '
                f'media-type="{_escape_attr(cover["media_type"])}" properties="cover-image"/>'
            )
            cover_meta = '<meta name="cover" content="cover-image"/>'

        creator_entries = []
        if creator:
            creator_entries.append(f'<dc:creator id="creator-aut">{escape(creator)}</dc:creator>')
            creator_entries.append(
                '<meta refines="#creator-aut" property="role" scheme="marc:relators">aut</meta>'
            )
        if illustrator:
            creator_entries.append(f'<dc:creator id="creator-ill">{escape(illustrator)}</dc:creator>')
            creator_entries.append(
                '<meta refines="#creator-ill" property="role" scheme="marc:relators">ill</meta>'
            )
        publisher_entry = f"<dc:publisher>{escape(publisher)}</dc:publisher>" if publisher else ""

        opf = _OPF_TEMPLATE.format(
            title=escape(volume_title),
            lang=language,
            identifier=escape(identifier) if identifier else f"urn:uuid:{uuid.uuid4()}",
            manifest="\n".join(manifest_items),
            spine="\n".join(spine_items),
            cover_meta=cover_meta,
            creator_entries="\n".join(creator_entries),
            publisher_entry=publisher_entry,
        )
        zf.writestr("OEBPS/content.opf", opf)

    return buf.getvalue()
