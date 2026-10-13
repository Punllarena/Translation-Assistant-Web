from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import Series, User, Volume
from api.models import Session as SessionRow
from api.routing import SESSION_STATE_ATTR
from api.security import token_hash

COOKIE_NAME = "ta_session"
LAST_SEEN_INTERVAL = timedelta(seconds=60)  # not a row write on every request


class UserOwned(Protocol):
    user_id: int


def db_session(request: Request) -> Iterator[Session]:
    """The request's session. It is committed by CommitOnResponseRoute, not here:
    this teardown runs after the response has been sent, where a failed commit
    could no longer be reported to the client (see api/routing.py)."""
    session = SessionLocal()
    setattr(request.state, SESSION_STATE_ATTR, session)
    try:
        yield session
    finally:
        session.rollback()  # no-op once committed; discards anything uncommitted
        session.close()


def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    row = db.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash(token)))
    now = datetime.now(UTC)
    if row is None or row.expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session invalid or expired")
    if row.last_seen_at is None or now - row.last_seen_at > LAST_SEEN_INTERVAL:
        row.last_seen_at = now
    return row.user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


def scoped[T: UserOwned](db: Session, model: type[T], obj_id: int, user_id: int) -> T:
    """Fetch a user-owned row or raise 404.

    404, never 403: a wrong owner and a missing row are indistinguishable
    to the caller, so existence is never disclosed. A model without a
    ``user_id`` column raises AttributeError (a programming error, loud) —
    checked before the lookup, or the common case of a non-existent id would
    answer 404 and hide the mistake.

    Single-row access only: list endpoints must filter by ``user_id`` inline
    (as ``list_profiles`` does).
    """
    if not hasattr(model, "user_id"):
        raise AttributeError(
            f"{model.__name__} has no user_id column; scoped() is for user-owned rows"
        )
    obj = db.get(model, obj_id)
    if obj is None or obj.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return obj


def owned_ref[T: UserOwned](
    db: Session, model: type[T], obj_id: int, user_id: int, field: str
) -> T:
    """``scoped()`` for an id named in a request *body* (series_id, profile_id, ...).

    The URL names the resource, so a bad reference in the body is a 422, not a 404,
    and "missing" and "someone else's" get one message, so existence stays undisclosed.
    """
    try:
        return scoped(db, model, obj_id, user_id)
    except HTTPException:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"{field}: no such item"
        ) from None


def scoped_volume(db: Session, volume_id: int, user_id: int) -> Volume:
    """A volume is owned through its series; 404 for missing and foreign alike."""
    volume = db.scalar(
        select(Volume).join(Series).where(Volume.id == volume_id, Series.user_id == user_id)
    )
    if volume is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return volume


def parse_zone(name: str) -> ZoneInfo:
    """An IANA zone name from the browser (Intl...timeZone); 422 for anything else,
    including path tricks such as "../../etc/passwd", which ZoneInfo rejects."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, f"tz: unknown time zone {name[:64]!r}"
        ) from exc


def zone(tz: str = Query("UTC", max_length=64)) -> ZoneInfo:
    return parse_zone(tz)
