"""The browser ta.db import (spec §6.4): a dry run, then the real run, on the job worker."""

import sqlite3

from api import tadb_uploads
from api.core.tadb_import import Refused, import_tadb
from api.jobs import JobContext, JobError, handler


def _result(dry: bool, report=None, refused: str | None = None) -> dict:
    return {
        "dry_run": dry, "refused": refused,
        "written": dict(report.written) if report else {},
        "skipped": dict(report.skipped) if report else {},
        "already_present": dict(report.already_present) if report else {},
        "messages": list(report.messages) if report else [],
    }


@handler("tadb_import")
def run_import(ctx: JobContext) -> dict:
    p, user_id = ctx.params, ctx.job.user_id
    dry = bool(p["dry_run"])
    path = tadb_uploads.path_for(user_id, p["upload_id"])
    keep = False  # only a finished dry run keeps the file for the real run
    try:
        if not path.is_file():
            raise JobError("The uploaded file is gone; upload it again.")
        ctx.progress(0, 1, "Checking the library" if dry else "Importing the library")
        try:
            report = import_tadb(ctx.db, path, user_id, dry_run=dry, force=bool(p["force"]))
        except Refused as exc:
            if not dry:
                raise JobError(str(exc)) from exc
            keep = True
            return _result(dry, refused=str(exc))
        except RuntimeError as exc:  # schema checks: "... not a desktop ta.db"
            raise JobError(str(exc)) from exc
        except sqlite3.DatabaseError as exc:
            raise JobError(f"not a desktop ta.db: {exc}") from exc
        keep = dry
        return _result(dry, report)
    finally:
        if not keep:
            path.unlink(missing_ok=True)
