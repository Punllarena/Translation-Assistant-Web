from fastapi import Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, owned_ref, scoped
from api.errors import conflict
from api.models import Profile, Series, User
from api.routing import api_router
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
    """Chapters survive: the ORM nulls their series_id, and the database's
    ON DELETE SET NULL clears volume_id as the series' volumes are deleted."""
    db.delete(scoped(db, Series, series_id, user.id))
    db.flush()
