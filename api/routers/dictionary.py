"""Admin → Dictionary (spec §5): status, upload, remove. Download is a job (api/dict_job.py)."""

from fastapi import Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import api.dict_job  # noqa: F401  registers the dict_download handler
from api import dictionary, jobs
from api.deps import db_session, require_admin
from api.models import Job, User
from api.routing import api_router
from api.schemas.dictionary import DictFileOut, DictionaryOut
from api.schemas.jobs import JobOut
from api.uploads import read_capped

router = api_router(prefix="/admin/dictionary", tags=["admin"])


def not_env(kind: dictionary.Kind) -> None:
    if dictionary.env_path(kind):
        var = "TA_EDICT_PATH" if kind == "edict" else "TA_CONJUGATIONS_PATH"
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"This file is set by {var} on the server; change it there.")


@router.get("", response_model=DictionaryOut)
def get_dictionary(_: User = Depends(require_admin)) -> dict:
    # sync def: FastAPI runs it in the threadpool, so the first (slow) index load is off the loop
    return {k: dictionary.status(k) for k in ("edict", "conjugations")}


@router.post("/edict/download", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def download(admin: User = Depends(require_admin), db: Session = Depends(db_session)) -> Job:
    not_env("edict")
    if db.scalar(select(Job.id).where(
        Job.kind == "dict_download", Job.state.in_(("queued", "running"))).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a dictionary download is already running")
    return jobs.enqueue(db, admin.id, "dict_download", {})


@router.post("/{kind}", response_model=DictFileOut)
def upload(kind: dictionary.Kind, file: UploadFile = File(...),
           _: User = Depends(require_admin)) -> dict:
    not_env(kind)
    data = read_capped(file, dictionary.MAX_UPLOAD)
    try:
        if kind == "edict":
            data = dictionary.gunzip_capped(data)
        dictionary.install(kind, data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    return dictionary.status(kind)


@router.delete("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def remove(kind: dictionary.Kind, _: User = Depends(require_admin)) -> None:
    not_env(kind)
    dictionary.remove(kind)
