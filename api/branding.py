"""Admin branding: the site's name, logos and favicon.

Two small tables: ``branding`` (one row) holds the name and the show-name flag; ``brand_images``
holds one row per uploaded file. Replacing an image deletes the old row and inserts a new one,
so an image id is a cache key that never changes meaning (the covers pattern).

Image types are decided by the bytes, never by the filename or the client's content type. SVG is
served with a sandboxing CSP and only ever shown through ``<img>`` / ``<link>``, never inline.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.models import BrandImage, Branding

DEFAULT_NAME = "Translation Assistant"
MAX_NAME = 60
MAX_IMAGE_BYTES = 1024 * 1024
KINDS = ("logo", "logo_dark", "favicon")
FAVICON = "favicon"
MEDIA_TYPES = {
    "png": "image/png",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "ico": "image/x-icon",
}
SVG_HEAD = 2048
SVG_PROLOGUES = ("<?xml", "<!doctype", "<!--")


def _svg(data: bytes) -> bool:
    """A document that starts with ``<svg``, or with a prolog followed by ``<svg`` and no
    ``<html`` before it. The BOM and leading whitespace are ignored."""
    text = data[:SVG_HEAD].decode("utf-8", errors="ignore").lstrip("\ufeff").lstrip().lower()
    if not text:
        return False
    if not text.startswith("<svg"):
        if not text.startswith(SVG_PROLOGUES):
            return False
        at = text.find("<svg")
        if at < 0 or "<html" in text[:at] or "</" in text[:at].replace("<!--", ""):
            return False
    after = text[text.find("<svg") + 4:][:1]
    return after in ("", " ", "\t", "\r", "\n", ">", "/")


def _magic(data: bytes, kind: str) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if kind == FAVICON and data[:4] == b"\x00\x00\x01\x00":
        return "ico"
    return None


def sniff_brand_image(data: bytes, kind: str) -> str | None:
    """``png``, ``webp``, ``svg``, or ``ico`` (favicon only); ``None`` for anything else."""
    return _magic(data, kind) or ("svg" if _svg(data) else None)


def media_type(data: bytes) -> str:
    """The type to serve stored bytes with, judged by the bytes."""
    sniffed = _magic(data, FAVICON)
    if sniffed is not None:
        return MEDIA_TYPES[sniffed]
    return "image/svg+xml" if _svg(data) else "application/octet-stream"


def clean_name(raw: str) -> str | None:
    """The trimmed name; ``None`` for blank, ValueError over 60 characters."""
    name = raw.strip()
    if not name:
        return None
    if len(name) > MAX_NAME:
        raise ValueError(f"name must be at most {MAX_NAME} characters")
    return name


def get(db: Session) -> Branding:
    """The branding row, created with the defaults on first read."""
    row = db.get(Branding, 1)
    if row is None:
        row = Branding(id=1, name=None, show_name=True)
        db.add(row)
        db.flush()
    return row


def set_text(db: Session, name: str | None, show_name: bool) -> Branding:
    row = get(db)
    row.name = name
    row.show_name = show_name
    db.flush()
    return row


def set_image(db: Session, kind: str, data: bytes) -> BrandImage:
    """Store ``data`` as the kind's image; the old row is deleted, so the id is new."""
    if kind not in KINDS:
        raise ValueError(f"unknown brand image kind {kind!r}")
    db.execute(delete(BrandImage).where(BrandImage.kind == kind))
    row = BrandImage(kind=kind, data=data)
    db.add(row)
    db.flush()
    return row


def clear_image(db: Session, kind: str) -> None:
    db.execute(delete(BrandImage).where(BrandImage.kind == kind))
    db.flush()


def reset(db: Session) -> None:
    """Back to the defaults: no name, the flag on, no images."""
    row = get(db)
    row.name = None
    row.show_name = True
    db.execute(delete(BrandImage))
    db.flush()


def public(db: Session) -> dict:
    """The public shape: the effective name (never blank) and the image ids."""
    row = get(db)
    ids = dict(db.execute(select(BrandImage.kind, BrandImage.id)).all())
    return {
        "name": row.name or DEFAULT_NAME,
        "show_name": row.show_name,
        "logo_id": ids.get("logo"),
        "logo_dark_id": ids.get("logo_dark"),
        "favicon_id": ids.get(FAVICON),
    }
