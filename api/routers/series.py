from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.core.text import natural_key
from api.deps import current_user, db_session, owned_ref, scoped
from api.errors import conflict
from api.library import arrange, chapters, renumber
from api.models import Document, Profile, Series, User
from api.routing import api_router
from api.schemas.documents import DocumentIds, DocumentOut
from api.schemas.series import SeriesCreate, SeriesOut, SeriesUpdate

router = api_router(prefix="/series", tags=["series"])

TITLE_TAKEN = "a series with that title exists"


@router.get("", response_model=list[SeriesOut])
def list_series(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Series]:
    return list(
        db.scalars(select(Series).where(Series.user_id == user.id).order_by(Series.title))
    )


@router.get("/{series_id}", response_model=SeriesOut)
def get_series(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Series:
    return scoped(db, Series, series_id, user.id)


@router.post("", response_model=SeriesOut, status_code=status.HTTP_201_CREATED)
def create_series(
    body: SeriesCreate, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Series:
    if body.profile_id is not None:
        owned_ref(db, Profile, body.profile_id, user.id, "profile_id")
    series = Series(user_id=user.id, **body.model_dump())
    try:
        with db.begin_nested():
            db.add(series)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    return series


@router.patch("/{series_id}", response_model=SeriesOut)
def update_series(
    series_id: int,
    body: SeriesUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Series:
    series = scoped(db, Series, series_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    if changes.get("profile_id") is not None:
        owned_ref(db, Profile, changes["profile_id"], user.id, "profile_id")
    try:
        with db.begin_nested():
            for field, value in changes.items():
                setattr(series, field, value)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    return series


@router.delete("/{series_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_series(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    """The series' chapters are deleted with it (lines and images by their cascades)."""
    db.delete(scoped(db, Series, series_id, user.id))
    db.flush()


def _refuse_syosetu(series: Series) -> None:
    if series.syosetu_url:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "chapter order follows the syosetu numbering"
        )


@router.put("/{series_id}/order", response_model=list[DocumentOut])
def reorder_chapters(
    series_id: int,
    body: DocumentIds,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[Document]:
    """Drag-and-drop reorder: the body lists every chapter of the series once, in the
    new order. A stale list (a chapter added meanwhile) is refused, not half-applied."""
    series = scoped(db, Series, series_id, user.id)
    _refuse_syosetu(series)
    by_id = {doc.id: doc for doc in chapters(db, series.id)}
    if sorted(body.document_ids) != sorted(by_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "document_ids must list every chapter of the series exactly once",
        )
    ordered = [by_id[doc_id] for doc_id in body.document_ids]
    renumber(ordered)
    db.flush()
    result = arrange(db, series)
    db.flush()
    return result


@router.post("/{series_id}/renumber", response_model=list[DocumentOut])
def renumber_by_title(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Document]:
    """series_order 1..N by natural sort ("Ch 2" before "Ch 10") of the title the
    desktop displays: chapter_title, else title."""
    series = scoped(db, Series, series_id, user.id)
    _refuse_syosetu(series)
    ordered = sorted(
        chapters(db, series.id), key=lambda d: natural_key(d.chapter_title or d.title)
    )
    renumber(ordered)
    db.flush()
    result = arrange(db, series)
    db.flush()
    return result
