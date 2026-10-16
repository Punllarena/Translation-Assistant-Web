"""The browser ta.db import (spec §6.4): a dry run, then the real run, on the job worker."""

import sqlite3

from api import tadb_uploads
from api.core.tadb_import import Refused, import_tadb, not_empty_preview
from api.jobs import JobContext, JobError, handler

# Messages are stored in the job row; a crafted file with millions of orphan rows must not
# make that row (or the SSE payload) millions of lines long.
MAX_MESSAGES = 200
ALREADY_IMPORTED = "This library was already imported into your account."


def _not_empty(existing: int) -> str:
    return (f"Your account already has {existing} chapter(s); "
            "chapters already present will be skipped.")


def _user_text(exc: Refused) -> str:
    """The browser's wording: no CLI flags, no server paths."""
    return _not_empty(exc.existing) if exc.existing else ALREADY_IMPORTED


def _result(dry: bool, report, refused: str | None) -> dict:
    preview = not_empty_preview(report.existing_documents)
    return {
        "dry_run": dry, "refused": refused,
        "written": dict(report.written),
        "skipped": dict(report.skipped),
        "already_present": dict(report.already_present),
        "messages": _capped([m for m in report.messages if m != preview]),
    }


def _capped(messages: list[str]) -> list[str]:
    extra = len(messages) - MAX_MESSAGES
    return messages[:MAX_MESSAGES] + [f"…and {extra} more"] if extra > 0 else messages


def _dry_run(ctx: JobContext, path, user_id: int, force: bool) -> dict:
    """Counts always; `refused` when a real run without force would be refused, so the
    SPA can offer Import anyway next to the numbers it is decided on."""
    try:
        report = import_tadb(ctx.db, path, user_id, dry_run=True, force=force)
    except Refused as exc:
        report = import_tadb(ctx.db, path, user_id, dry_run=True, force=True)
        return _result(True, report, _user_text(exc))
    refused = None if force or not report.existing_documents else _not_empty(
        report.existing_documents)
    return _result(True, report, refused)


@handler("tadb_import")
def run_import(ctx: JobContext) -> dict:
    p, user_id = ctx.params, ctx.job.user_id
    dry, force = bool(p["dry_run"]), bool(p["force"])
    path = tadb_uploads.path_for(user_id, p["upload_id"])
    keep = False  # only a finished dry run keeps the file for the real run
    try:
        if not path.is_file():
            raise JobError("The uploaded file is gone; upload it again.")
        ctx.progress(0, 1, "Checking the library" if dry else "Importing the library")
        try:
            if dry:
                result = _dry_run(ctx, path, user_id, force)
                keep = True
                return result
            return _result(False, import_tadb(ctx.db, path, user_id, force=force), None)
        except Refused as exc:
            raise JobError(_user_text(exc)) from exc
        except RuntimeError as exc:  # schema checks: "... not a desktop ta.db"
            raise JobError(str(exc)) from exc
        except sqlite3.DatabaseError as exc:
            raise JobError(f"not a desktop ta.db: {exc}") from exc
    finally:
        if not keep:
            path.unlink(missing_ok=True)
