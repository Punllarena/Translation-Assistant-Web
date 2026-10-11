"""Reading uploads: a hard size cap, and image types decided by content, not by the
client's Content-Type."""

from fastapi import HTTPException, UploadFile, status


def read_capped(upload: UploadFile, limit: int) -> bytes:
    """The upload's bytes, or 413 if it is larger than ``limit``.

    Starlette has already spooled the body (to disk past 1 MB), so this bounds what
    reaches memory and the database, not what crossed the network.
    # Caddy caps request bodies at 12 MB before they reach uvicorn (web/Caddyfile).
    """
    data = upload.file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, f"upload exceeds {limit} bytes")
    return data


def sniff_image(data: bytes) -> str | None:
    """The file extension for a PNG, JPEG, GIF, or WebP, judged by magic bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None
