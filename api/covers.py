"""Volume covers: storing one, downloading one from an image address, and the series cover.

The link download is the SSRF-sensitive part: every hop, redirects included, passes
``check_url`` before it is sent, and the body is read with a hard cap."""

from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.models import Volume, VolumeCover
from api.mt.urls import check_user_url
from api.uploads import sniff_image

MAX_IMAGE_BYTES = 10 * 1024 * 1024
TIMEOUT = 20.0
MAX_REDIRECTS = 3
PAGE_LINK = ("That link is a web page, not an image. Open the image, right-click it and "
             "copy the image address.")
NOT_IMAGE = "cover must be a PNG, JPEG, GIF or WebP image"

check_url = check_user_url  # the seam tests replace (it resolves DNS)


class CoverFetchError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code, self.message = status_code, message


def _check(request: httpx.Request) -> None:
    error = check_url(str(request.url), False, "image")
    if error:
        raise CoverFetchError(422, error)


def client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    return httpx.Client(
        transport=transport, timeout=TIMEOUT, follow_redirects=True,
        max_redirects=MAX_REDIRECTS, headers={"User-Agent": "Mozilla/5.0"},
        event_hooks={"request": [_check]},
    )


def fetch_image(c: httpx.Client, url: str) -> tuple[bytes, str]:
    """The image at ``url`` and its file extension; CoverFetchError otherwise."""
    url = url.strip()
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in url):
        raise CoverFetchError(422, "The address contains control characters.")
    host = urlsplit(url).hostname or url
    try:
        with c.stream("GET", url) as r:
            if r.status_code != 200:
                raise CoverFetchError(502, f"{host} answered HTTP {r.status_code}.")
            data = bytearray()
            for chunk in r.iter_bytes():
                data += chunk
                if len(data) > MAX_IMAGE_BYTES:
                    raise CoverFetchError(413, f"The image is larger than {MAX_IMAGE_BYTES} bytes.")
            content_type = r.headers.get("content-type", "")
    except httpx.TooManyRedirects:
        raise CoverFetchError(422, "That address redirects too many times.") from None
    except httpx.InvalidURL as exc:
        raise CoverFetchError(422, f"Not a valid address: {exc}") from None
    except httpx.UnsupportedProtocol:
        raise CoverFetchError(422, "That image URL is not a valid http(s) address.") from None
    except httpx.HTTPError as exc:
        raise CoverFetchError(502, f"Could not reach {host} ({type(exc).__name__}).") from None
    ext = sniff_image(bytes(data))
    if ext is None:
        if "html" in content_type.lower():
            raise CoverFetchError(422, PAGE_LINK)
        raise CoverFetchError(415, NOT_IMAGE)
    return bytes(data), ext


def set_cover(db: Session, volume_id: int, data: bytes, src_path: str) -> VolumeCover:
    """Replace the volume's cover (a new row, so a new id)."""
    db.execute(delete(VolumeCover).where(VolumeCover.volume_id == volume_id))
    cover = VolumeCover(volume_id=volume_id, src_path=src_path, data=data)
    db.add(cover)
    db.flush()
    forget(db, volume_id)
    return cover


def clear_cover(db: Session, volume_id: int) -> None:
    db.execute(delete(VolumeCover).where(VolumeCover.volume_id == volume_id))
    forget(db, volume_id)


def forget(db: Session, volume_id: int) -> None:
    """Volume.cover_id is a SQL expression loaded with the row; reload it on next access."""
    volume = db.get(Volume, volume_id)
    if volume is not None:
        db.expire(volume, ["cover_id"])


def volume_cover(db: Session, volume_id: int) -> VolumeCover | None:
    return db.scalar(select(VolumeCover).where(VolumeCover.volume_id == volume_id))


def effective_series_cover(db: Session, series_id: int) -> VolumeCover | None:
    """The chosen volume's cover, else the first volume's (by volume order) that has one."""
    return db.scalar(
        select(VolumeCover).join(Volume, Volume.id == VolumeCover.volume_id)
        .where(Volume.series_id == series_id)
        .order_by(Volume.is_series_cover.desc(), Volume.volume_order, Volume.id)
        .limit(1)
    )


def cover_dict(cover: VolumeCover) -> dict:
    """The shape publish and EPUB code pass around for an image."""
    return {"id": cover.id, "anchor_position": 0, "src_path": cover.src_path, "data": cover.data}
