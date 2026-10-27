"""The uploaded backup file waiting for its restore (spec "Restore flow"). Streamed to
disk: a whole server can be gigabytes. The restore deletes its own file when it ends; this
sweep only catches uploads whose request died (never started, or a crash)."""

import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status

from api.config import get_settings

MAX_BACKUP_BYTES = 4 << 30  # the Caddy route caps the request body too


def _root() -> Path:
    return Path(get_settings().data_dir) / "uploads" / "restore"


def save(upload: UploadFile) -> Path:
    """Copy the upload under uploads/restore/ and return its path.

    Starlette has already spooled the multipart body before the handler runs, so this cap
    bounds what is kept here, not what crossed the network (Caddy caps that at 4 GiB)."""
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    dest = root / f"{uuid4().hex}.zip"
    total = 0
    try:
        with dest.open("wb") as out:
            while chunk := upload.file.read(1 << 20):
                total += len(chunk)
                if total > MAX_BACKUP_BYTES:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                                        f"upload exceeds {MAX_BACKUP_BYTES} bytes")
                out.write(chunk)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return dest


def sweep(max_age: timedelta = timedelta(hours=24)) -> int:
    """Delete restore uploads older than max_age. Returns how many."""
    cutoff, n = time.time() - max_age.total_seconds(), 0
    for path in _root().glob("*.zip"):
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                n += 1
        except FileNotFoundError:
            pass
    return n
