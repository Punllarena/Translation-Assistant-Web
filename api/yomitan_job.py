"""Install a Yomitan dictionary zip (spec "Upload and storage"). The zip is streamed to
disk by the route and read by the job; the whole install is one transaction in the job's
session, so progress goes through ``report`` (job row only), never ``progress``."""

import time
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, UploadFile, status

from api import yomitan_store
from api.config import get_settings
from api.core import yomitan_read
from api.core.yomitan_read import YomitanError
from api.jobs import JobContext, JobError, handler

MAX_UPLOAD = 64 * 1024 * 1024
MAGIC = b"PK\x03\x04"


def upload_dir() -> Path:
    return Path(get_settings().data_dir) / "uploads" / "yomitan"


def _path(upload: str) -> Path:
    return upload_dir() / f"{UUID(upload).hex}.zip"


def save_upload(file: UploadFile) -> str:
    """Stream the upload to ``<hex>.zip`` and return the hex id."""
    upload_id = uuid4().hex
    dest = _path(upload_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with dest.open("wb") as out:
            while chunk := file.file.read(1 << 20):
                total += len(chunk)
                if total > MAX_UPLOAD:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE,
                                        f"upload exceeds {MAX_UPLOAD} bytes")
                out.write(chunk)
        with dest.open("rb") as f:
            if f.read(len(MAGIC)) != MAGIC:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                                    yomitan_read.NOT_A_ZIP)
    except BaseException:
        dest.unlink(missing_ok=True)
        raise
    return upload_id


def sweep(max_age: timedelta = timedelta(hours=24)) -> int:
    """Delete uploads older than max_age (jobs that never ran). Returns how many."""
    cutoff, n = time.time() - max_age.total_seconds(), 0
    for p in upload_dir().glob("*.zip"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
                n += 1
        except FileNotFoundError:
            pass
    return n


@handler("yomitan_import")
def import_dictionary(ctx: JobContext) -> dict:
    try:
        path = _path(str(ctx.params.get("upload", "")))
    except ValueError:
        raise JobError("The uploaded file is gone; upload it again.") from None
    if not path.is_file():
        raise JobError("The uploaded file is gone; upload it again.")
    seen = [1]

    def on_bank(done: int, total: int, name: str) -> None:
        seen[0] = max(total, 1)
        ctx.report(done, total, f"Reading {name}")

    try:
        parsed = yomitan_read.read(path, on_bank=on_bank)
        ctx.report(seen[0], seen[0], "Saving")
        result = yomitan_store.install(
            ctx.db, parsed, on_batch=lambda i, n: ctx.report(i, n, "Saving"))
    except YomitanError as exc:
        raise JobError(str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)
    d = result.dictionary
    noun = "entry" if d.entry_count == 1 else "entries"
    if result.replaced_revision is None:
        message = f"Installed {d.title} ({d.entry_count:,} {noun})"
    else:
        message = f"Updated {d.title} from {result.replaced_revision} to {d.revision}"
    return {"dictionary_id": d.id, "title": d.title, "revision": d.revision,
            "entries": d.entry_count, "skipped_rows": parsed.skipped_rows, "message": message}
