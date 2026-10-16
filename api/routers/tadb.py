"""Import a desktop ta.db from the browser (spec §6)."""

from fastapi import Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import api.tadb_job  # noqa: F401  registers the tadb_import handler
from api import jobs, tadb_uploads
from api.deps import current_user, db_session
from api.models import Job, User
from api.routing import api_router
from api.schemas.jobs import JobOut
from api.schemas.tadb import TadbRunIn, TadbUploadOut

router = api_router(prefix="/import/tadb", tags=["transfer"])


def _not_busy(db: Session, user_id: int) -> None:
    if db.scalar(select(Job.id).where(
        Job.user_id == user_id, Job.kind == "tadb_import",
        Job.state.in_(("queued", "running"))).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a ta.db import is already running")


def _path(user_id: int, upload_id: str):
    try:
        return tadb_uploads.path_for(user_id, upload_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found") from None


@router.post("", response_model=TadbUploadOut, status_code=status.HTTP_202_ACCEPTED)
def upload(file: UploadFile = File(...), user: User = Depends(current_user),
           db: Session = Depends(db_session)) -> TadbUploadOut:
    _not_busy(db, user.id)
    tadb_uploads.sweep()  # abandoned uploads of any user, not only at startup
    upload_id = tadb_uploads.save(user.id, file)
    job = jobs.enqueue(db, user.id, "tadb_import",
                       {"upload_id": upload_id, "dry_run": True, "force": False})
    return TadbUploadOut(upload_id=upload_id, job_id=job.id)


@router.post("/{upload_id}/run", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def run(upload_id: str, body: TadbRunIn, user: User = Depends(current_user),
        db: Session = Depends(db_session)) -> Job:
    if not _path(user.id, upload_id).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "upload not found")
    _not_busy(db, user.id)
    return jobs.enqueue(db, user.id, "tadb_import",
                        {"upload_id": upload_id, "dry_run": False, "force": body.force})


@router.delete("/{upload_id}", status_code=status.HTTP_204_NO_CONTENT)
def discard(upload_id: str, user: User = Depends(current_user)) -> None:
    _path(user.id, upload_id).unlink(missing_ok=True)
