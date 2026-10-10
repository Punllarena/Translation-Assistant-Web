from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db import SessionLocal
from api.models import Session as SessionRow
from api.models import User
from api.security import token_hash

COOKIE_NAME = "ta_session"


def db_session() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_user(request: Request, db: Session = Depends(db_session)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    row = db.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash(token)))
    now = datetime.now(UTC)
    if row is None or row.expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "session invalid or expired")
    row.last_seen_at = now
    return row.user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


def scoped[T](db: Session, model: type[T], obj_id: int, user_id: int) -> T:
    """Fetch a user-owned row or raise 404.

    404, never 403: a wrong owner and a missing row are indistinguishable
    to the caller, so existence is never disclosed.
    """
    obj = db.get(model, obj_id)
    if obj is None or getattr(obj, "user_id", None) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return obj
