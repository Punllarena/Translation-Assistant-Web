"""Shrink oversized images before they go into a WordPress publish payload, from the
desktop translation_assistant/imageopt.py (Pillow instead of Qt).

EasyWP's proxy resets any request whose body exceeds ~1 MB, and EPUB covers / colour
plates are 500-750 KB JPEGs that base64-inflate past that on their own."""

import io

from PIL import Image

_QUALITY_STEPS = (82, 70, 60, 50, 40)


def shrink_image(data: bytes, max_dim: int = 1600, target_bytes: int = 350_000) -> bytes:
    """A smaller JPEG rendering of ``data``.

    Returns ``data`` unchanged (same object) when it is already under ``target_bytes``,
    cannot be decoded (decompression bombs included), or no re-encoding beats the original.
    """
    if len(data) <= target_bytes:
        return data
    try:
        with Image.open(io.BytesIO(data)) as im:
            # thumbnail keeps aspect and never enlarges
            im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            img = im.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError):
        return data
    out = b""
    for quality in _QUALITY_STEPS:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        out = buf.getvalue()
        if len(out) <= target_bytes:
            return out
    return out if out and len(out) < len(data) else data
