"""Download a whole-server backup, and restore one (spec "Backup and restore").

The restore is refused while any job is queued or running or any out-of-request writer is in
flight, and the check runs again after the upload, atomically with switching maintenance on:
nothing that started while the file was arriving may commit into the new database.
"""

from dataclasses import asdict
from datetime import date

from fastapi import Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from api import accounts
from api.backup import crypto, export, restore, schema, state, uploads
from api.backup.crypto import WRONG_PASSPHRASE, WrongPassphrase
from api.backup.manifest import BackupInvalid
from api.deps import db_session, require_admin
from api.models import User
from api.routers.transfer import attachment
from api.routing import api_router
from api.schemas.backup import RestoreStatusOut

router = api_router(tags=["backup"])

NOT_AT_HEAD = "The database is not at the latest migration; upgrade it before taking a backup."
CONFIRM = "Type RESTORE to confirm."


def _status() -> RestoreStatusOut:
    return RestoreStatusOut(**asdict(state.snapshot()))


@router.post("/admin/backup")
def download_backup(
    passphrase: str = Form(...),
    _: User = Depends(require_admin),
    db: Session = Depends(db_session),
) -> Response:
    """The whole server as one zip, streamed so the browser writes it to disk."""
    if state.active():
        raise HTTPException(status.HTTP_409_CONFLICT, state.RESTORING)
    if schema.current_revision(db.connection()) != schema.head():
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_AT_HEAD)
    if len(passphrase) < accounts.MIN_PASSWORD:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            f"Use at least {accounts.MIN_PASSWORD} characters.")
    kdf = crypto.new_kdf()
    f = crypto.derive(passphrase, kdf)
    return StreamingResponse(
        export.stream(f, kdf),
        media_type="application/zip",
        headers=attachment(export.filename(date.today())),
    )


def _start(
    db: Session, upload: UploadFile, passphrase: str, *, from_setup: bool
) -> RestoreStatusOut:
    """Save the upload, validate it, then win the admission gate and start the thread."""
    if state.active():  # a cheap early answer; the real guard is try_begin below
        raise HTTPException(status.HTTP_409_CONFLICT, state.RESTORING)
    if state.busy(db):
        raise HTTPException(status.HTTP_409_CONFLICT, state.BUSY)
    path = uploads.save(upload)
    try:
        reader = restore.BackupReader.open(path, passphrase)
    except (BackupInvalid, WrongPassphrase) as exc:
        path.unlink(missing_ok=True)
        message = WRONG_PASSPHRASE if isinstance(exc, WrongPassphrase) else str(exc)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, message) from None
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    reason = state.try_begin(db)
    if reason is not None:  # something started while the file was arriving
        reader.close()
        path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_409_CONFLICT, reason)
    restore.start(reader, from_setup)
    return _status()


@router.post("/admin/restore", response_model=RestoreStatusOut,
             status_code=status.HTTP_202_ACCEPTED)
def restore_admin(
    file: UploadFile = File(...),
    passphrase: str = Form(...),
    confirm: str = Form(""),
    _: User = Depends(require_admin),
    db: Session = Depends(db_session),
) -> RestoreStatusOut:
    if confirm != "RESTORE":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, CONFIRM)
    return _start(db, file, passphrase, from_setup=False)


@router.post("/setup/restore", response_model=RestoreStatusOut,
             status_code=status.HTTP_202_ACCEPTED)
def restore_setup(
    file: UploadFile = File(...), passphrase: str = Form(...),
    db: Session = Depends(db_session),
) -> RestoreStatusOut:
    """The setup wizard's choice, open while no user exists (the same trust as /setup/admin)."""
    if not accounts.needs_setup(db):
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Setup is already complete; sign in instead.")
    return _start(db, file, passphrase, from_setup=True)


@router.get("/restore/status", response_model=RestoreStatusOut)
def restore_status() -> RestoreStatusOut:
    """No login: the SPA polls it while every other route answers 503."""
    return _status()
