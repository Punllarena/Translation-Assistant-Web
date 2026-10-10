from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped
from api.errors import conflict
from api.models import Profile, User
from api.routing import api_router
from api.schemas.profiles import ProfileCreate, ProfileOut, ProfileUpdate

router = api_router(prefix="/profiles", tags=["profiles"])


NAME_TAKEN = "a profile with that name exists"


@router.get("", response_model=list[ProfileOut])
def list_profiles(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Profile]:
    return list(
        db.scalars(select(Profile).where(Profile.user_id == user.id).order_by(Profile.name))
    )


@router.get("/{profile_id}", response_model=ProfileOut)
def get_profile(
    profile_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Profile:
    return scoped(db, Profile, profile_id, user.id)


@router.post("", response_model=ProfileOut, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: ProfileCreate, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Profile:
    profile = Profile(
        user_id=user.id,
        name=body.name,
        parse_chars=body.parse_chars,
        is_default=body.is_default,
    )
    # SAVEPOINT: a duplicate name undoes only this insert, never the rest of
    # the request's work (e.g. the session's last_seen_at touch).
    try:
        with db.begin_nested():
            db.add(profile)
    except IntegrityError as exc:
        raise conflict(exc, NAME_TAKEN) from exc
    return profile


@router.patch("/{profile_id}", response_model=ProfileOut)
def update_profile(
    profile_id: int,
    body: ProfileUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Profile:
    profile = scoped(db, Profile, profile_id, user.id)
    try:
        with db.begin_nested():
            for field, value in body.model_dump(exclude_unset=True).items():
                setattr(profile, field, value)
    except IntegrityError as exc:
        raise conflict(exc, NAME_TAKEN) from exc
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    profile = scoped(db, Profile, profile_id, user.id)
    remaining = db.scalar(
        select(Profile.id).where(Profile.user_id == user.id, Profile.id != profile_id).limit(1)
    )
    if remaining is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "cannot delete the only profile")
    db.delete(profile)
    db.flush()
