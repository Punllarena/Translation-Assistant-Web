"""Admin → Dictionary (spec §5): status, upload, remove. Download is a job (api/dict_job.py)."""

from fastapi import Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

import api.dict_job  # noqa: F401  registers the dict_download handler
from api import dictionary, jobs, yomitan_job, yomitan_store
from api.deps import db_session, require_admin
from api.models import Job, User
from api.routing import api_router
from api.schemas.dictionary import DictFileOut, DictionaryOut, OrderIn, OrderOut, YomitanDictOut
from api.schemas.jobs import JobOut
from api.uploads import read_capped

router = api_router(prefix="/admin/dictionary", tags=["admin"])


def not_env(kind: dictionary.Kind) -> None:
    if dictionary.env_path(kind):
        var = "TA_EDICT_PATH" if kind == "edict" else "TA_CONJUGATIONS_PATH"
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"This file is set by {var} on the server; change it there.")


@router.get("", response_model=DictionaryOut)
def get_dictionary(_: User = Depends(require_admin), db: Session = Depends(db_session)) -> dict:
    # sync def: FastAPI runs it in the threadpool, so the first (slow) index load is off the loop
    return {
        **{k: dictionary.status(k) for k in ("edict", "conjugations")},
        "yomitan": [
            YomitanDictOut(
                id=d.id, title=d.title, revision=d.revision, attribution=d.attribution,
                author=d.author, url=d.url, entries=d.entry_count, installed_at=d.installed_at)
            for d in yomitan_store.installed(db)
        ],
        "order": yomitan_store.order(db),
    }


@router.post("/edict/download", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def download(admin: User = Depends(require_admin), db: Session = Depends(db_session)) -> Job:
    not_env("edict")
    if db.scalar(select(Job.id).where(
        Job.kind == "dict_download", Job.state.in_(("queued", "running"))).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a dictionary download is already running")
    return jobs.enqueue(db, admin.id, "dict_download", {})


@router.post("/yomitan", response_model=JobOut, status_code=status.HTTP_202_ACCEPTED)
def upload_yomitan(file: UploadFile = File(...), admin: User = Depends(require_admin),
                   db: Session = Depends(db_session)) -> Job:
    if db.scalar(select(Job.id).where(
        Job.kind == "yomitan_import", Job.state.in_(("queued", "running"))).limit(1)):
        raise HTTPException(status.HTTP_409_CONFLICT, "a dictionary upload is already running")
    upload_id = yomitan_job.save_upload(file)
    return jobs.enqueue(db, admin.id, "yomitan_import", {"upload": upload_id})


@router.put("/order", response_model=OrderOut)
def put_order(body: OrderIn, admin: User = Depends(require_admin),
              db: Session = Depends(db_session)) -> dict:
    try:
        return {"order": yomitan_store.set_order(db, body.order, admin.id)}
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/yomitan/{dictionary_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_yomitan(dictionary_id: int, _: User = Depends(require_admin),
                   db: Session = Depends(db_session)) -> None:
    if not yomitan_store.remove(db, dictionary_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "dictionary not found")


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
