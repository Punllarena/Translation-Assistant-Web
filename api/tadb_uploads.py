"""Uploaded desktop ta.db files waiting for their import (spec §6). Streamed to disk:
a library with images can be hundreds of MB."""

import time
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from api.config import get_settings

MAX_TADB_BYTES = 1 << 30
MAGIC = b"SQLite format 3\x00"


def _root() -> Path:
    return Path(get_settings().data_dir) / "uploads"


def path_for(user_id: int, upload_id: str) -> Path:
    """The file for this user's upload id (it may not exist). ValueError for a malformed id."""
    return _root() / str(user_id) / f"{UUID(upload_id).hex}.db"


def save(user_id: int, upload: UploadFile) -> str:
    """Copy the upload to disk and return its id. Call only once the user has no active
    import: the user's other pending uploads are deleted first (one per user).

    Starlette has already spooled the multipart body before the handler runs, so the cap
    bounds what is kept here, not what crossed the network (Caddy caps that at 1 GiB)."""
    upload_id = uuid4().hex
    dest = path_for(user_id, upload_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    for old in dest.parent.glob("*.db"):
        old.unlink(missing_ok=True)
    total = 0
    try:
        with dest.open("wb") as out:
            while chunk := upload.file.read(1 << 20):
                total += len(chunk)
                if total > MAX_TADB_BYTES:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                                        f"upload exceeds {MAX_TADB_BYTES} bytes")
                out.write(chunk)
        with dest.open("rb") as f:
            if f.read(len(MAGIC)) != MAGIC:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    "This is not a SQLite database; choose the desktop ta.db.")
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return upload_id


def sweep(max_age: timedelta = timedelta(hours=24)) -> int:
    """Delete uploads older than max_age (abandoned dry runs). Returns how many."""
    cutoff, n = time.time() - max_age.total_seconds(), 0
    for p in _root().glob("*/*.db"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                n += 1
        except FileNotFoundError:
            pass
    return n
