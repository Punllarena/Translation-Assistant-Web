"""Account creation shared by the setup wizard, the seed CLI and login's session start."""

from datetime import UTC, datetime, timedelta

from fastapi import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.deps import COOKIE_NAME
from api.models import Profile, User
from api.models import Session as SessionRow
from api.security import hash_password, new_token, token_hash

MIN_PASSWORD = 12
USERNAME_PATTERN = r"^[A-Za-z0-9_.-]{3,32}$"  # no "@", so a login string is one or the other
# Any constant works; it only has to be the same for every claim (pg_advisory_xact_lock key).
SETUP_LOCK = 0x7461_5345_5455


class AlreadySetUp(Exception):
    """A user exists, so the first-admin claim is closed."""


def find_by_username(db: Session, username: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.username) == username.lower()))


def create_admin(db: Session, email: str, password: str, username: str | None = None) -> User:
    email = email.strip().lower()
    username = username or email.split("@")[0][:32]
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError(f"user {email} already exists")
    if find_by_username(db, username) is not None:
        raise ValueError(f"username {username} is taken")
    user = User(
        email=email, username=username, password_hash=hash_password(password), is_admin=True
    )
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    db.flush()
    return user


def needs_setup(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is None


def claim_first_admin(db: Session, email: str, password: str, username: str) -> User:
    """Create the first admin, or raise AlreadySetUp. The transaction-scoped advisory lock
    serialises concurrent claims: the second waits, then sees the first's user."""
    db.execute(select(func.pg_advisory_xact_lock(SETUP_LOCK)))
    if not needs_setup(db):
        raise AlreadySetUp
    return create_admin(db, email, password, username)


def start_session(db: Session, response: Response, user: User) -> None:
    settings = get_settings()
    token = new_token()
    db.add(SessionRow(
        token_hash=token_hash(token),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(days=settings.session_ttl_days),
    ))
    db.flush()
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, samesite="lax", secure=settings.cookie_secure,
        max_age=settings.session_ttl_days * 86400, path="/",
    )
