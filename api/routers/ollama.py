"""Ollama background translation: the run queue, Run now, and flushing held suggestions."""

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.exc import StaleDataError

from api import jobs
from api.deps import current_user, db_session, scoped, scoped_volume
from api.models import Document, Job, Series, User, UserSetting, Volume
from api.models.ollama import OllamaChunk, OllamaQueueItem
from api.ollama import endpoint, runlog, store, work
from api.routing import api_router
from api.schemas.jobs import JobOut
from api.schemas.ollama import (
    FlushIn,
    FlushOut,
    QueueItemIn,
    QueueItemOut,
    QueueOrder,
    RunLogEntry,
    RunLogOut,
)

router = api_router(prefix="/ollama", tags=["ollama"])

QUEUE_MAX = 100
ESTIMATE_WINDOW = timedelta(days=30)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


def _items(db: Session, user_id: int) -> list[OllamaQueueItem]:
    return list(
        db.scalars(
            select(OllamaQueueItem)
            .where(OllamaQueueItem.user_id == user_id)
            .order_by(OllamaQueueItem.position, OllamaQueueItem.id)
        )
    )


def _ms_per_line(db: Session, user_id: int) -> float | None:
    """Average total_ms per asked line over recent ok chunks of the current model and size."""
    model = db.scalar(
        select(UserSetting.value_json).where(
            UserSetting.user_id == user_id, UserSetting.key == "ollama_model"
        )
    )
    if not isinstance(model, str) or not model:
        return None
    size = endpoint.prefs_for(db, user_id).chunk_lines
    avg = db.scalar(
        select(func.avg(OllamaChunk.total_ms * 1.0 / OllamaChunk.asked)).where(
            OllamaChunk.user_id == user_id,
            OllamaChunk.ok.is_(True),
            OllamaChunk.model == model,
            OllamaChunk.chunk_lines == size,
            OllamaChunk.asked > 0,
            OllamaChunk.total_ms.is_not(None),
            OllamaChunk.created_at >= datetime.now(UTC) - ESTIMATE_WINDOW,
        )
    )
    return None if avg is None else float(avg)


def _out(db: Session, user_id: int, item: OllamaQueueItem, ms: float | None) -> QueueItemOut:
    series = db.get(Series, item.series_id)
    volume = db.get(Volume, item.volume_id) if item.volume_id else None
    if item.kind == "series":
        label = series.title
    elif item.kind == "volume":
        label = volume.label if volume else series.title
    elif len(item.document_ids) == 1:
        doc = db.get(Document, item.document_ids[0])
        label = doc.title if doc else "1 chapter"
    else:
        label = f"{len(item.document_ids)} chapters"
    left = work.lines_left(db, user_id, item)
    return QueueItemOut(
        id=item.id,
        kind=item.kind,
        series_id=item.series_id,
        series_title=series.title,
        volume_id=item.volume_id,
        volume_label=volume.label if volume else None,
        document_ids=list(item.document_ids),
        label=label,
        lines_left=left,
        estimate_seconds=None if ms is None else round(left * ms / 1000),
    )


def _listing(db: Session, user_id: int) -> list[QueueItemOut]:
    ms = _ms_per_line(db, user_id)
    return [_out(db, user_id, item, ms) for item in _items(db, user_id)]


@router.get("/queue", response_model=list[QueueItemOut])
def get_queue(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[QueueItemOut]:
    return _listing(db, user.id)


@router.post("/queue", response_model=QueueItemOut, status_code=status.HTTP_201_CREATED)
def add_to_queue(
    body: QueueItemIn,
    response: Response,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> QueueItemOut:
    scoped(db, Series, body.series_id, user.id)
    volume_id = body.volume_id
    if body.kind == "volume":
        if volume_id is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "volume_id is required")
        if scoped_volume(db, volume_id, user.id).series_id != body.series_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    else:
        volume_id = None
    doc_ids: list[int] = []
    if body.kind == "documents":
        doc_ids = sorted(set(body.document_ids))
        if not doc_ids:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "document_ids is empty")
        found = set(
            db.scalars(
                select(Document.id).where(
                    Document.id.in_(doc_ids),
                    Document.user_id == user.id,
                    Document.series_id == body.series_id,
                )
            )
        )
        if found != set(doc_ids):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    existing = _items(db, user.id)
    for item in existing:
        if (item.kind, item.series_id, item.volume_id, sorted(item.document_ids)) == (
            body.kind, body.series_id, volume_id, doc_ids,
        ):
            response.status_code = status.HTTP_200_OK
            return _out(db, user.id, item, _ms_per_line(db, user.id))
    if len(existing) >= QUEUE_MAX:
        raise _conflict(f"The queue holds at most {QUEUE_MAX} items.")
    item = OllamaQueueItem(
        user_id=user.id, kind=body.kind, series_id=body.series_id, volume_id=volume_id,
        document_ids=doc_ids, position=max((i.position for i in existing), default=-1) + 1,
    )
    db.add(item)
    db.flush()
    return _out(db, user.id, item, _ms_per_line(db, user.id))


@router.put("/queue/order", response_model=list[QueueItemOut])
def reorder_queue(
    body: QueueOrder, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[QueueItemOut]:
    items = {item.id: item for item in _items(db, user.id)}
    if len(body.ids) != len(set(body.ids)) or set(body.ids) != set(items):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "ids must be exactly the queued items"
        )
    for position, item_id in enumerate(body.ids):
        items[item_id].position = position
    try:
        db.flush()
    except StaleDataError:  # the runner removed a finished item meanwhile
        raise _conflict("The queue changed; reload it and try again.") from None
    return _listing(db, user.id)


@router.delete("/queue/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_queue(
    item_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Response:
    db.delete(scoped(db, OllamaQueueItem, item_id, user.id))
    db.flush()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/run", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def run_now(user: User = Depends(current_user), db: Session = Depends(db_session)) -> Job:
    """Start a run that works through the queue until it is drained."""
    _, setup = endpoint.load(db, user.id)
    if setup:
        raise _conflict(setup)
    if not _items(db, user.id):
        raise _conflict("The queue is empty.")
    try:
        with db.begin_nested():
            return jobs.enqueue(db, user.id, "ollama_run", params={})
    except IntegrityError:
        raise _conflict("An Ollama run is already active.") from None


@router.get("/runs/{job_id}/log", response_model=RunLogOut)
def run_log(
    job_id: int, after: int = Query(0, ge=0),
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> RunLogOut:
    """What a run has been doing: the entries after `after`, kept in memory (api/ollama/runlog)."""
    job = scoped(db, Job, job_id, user.id)
    if job.kind != "ollama_run":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    snap = runlog.read(job.id, after)
    if snap is None:
        return RunLogOut(kept=False, entries=[], now=None, ended=True, next=after)
    entries = [RunLogEntry(seq=e.seq, at=e.at, level=e.level, text=e.text) for e in snap.entries]
    return RunLogOut(kept=True, entries=entries, now=snap.now, ended=snap.ended, next=snap.next)


@router.post("/flush", response_model=FlushOut)
def flush_suggestions(
    body: FlushIn, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> FlushOut:
    # another user's (or a missing) target is 404, as everywhere else
    if body.series_id is not None:
        scoped(db, Series, body.series_id, user.id)
    if body.volume_id is not None:
        scoped_volume(db, body.volume_id, user.id)
    if body.document_ids:
        ids = set(body.document_ids)
        owned = db.scalars(
            select(Document.id).where(Document.id.in_(ids), Document.user_id == user.id)
        )
        if set(owned) != ids:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    cleared = store.flush(
        db, user.id, document_ids=body.document_ids, volume_id=body.volume_id,
        series_id=body.series_id,
    )
    return FlushOut(cleared=cleared)
