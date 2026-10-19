"""Admin account creation, shared by `tools.seed_admin` and the first-run setup page."""

import base64
import hashlib
import hmac

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.models import Profile, User
from api.security import hash_password

MIN_PASSWORD = 12


def create_admin(db: Session, email: str, password: str) -> User:
    email = email.strip().lower()
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"password must be at least {MIN_PASSWORD} characters")
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise ValueError(f"user {email} already exists")
    user = User(email=email, password_hash=hash_password(password), is_admin=True)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    db.flush()
    return user


def has_users(db: Session) -> bool:
    return db.scalar(select(User.id).limit(1)) is not None


def setup_token() -> str:
    """The first-run setup token. Derived from TA_SECRET_KEY, so it survives restarts without
    being stored; only the operator (who can read the server log or the key) knows it, which
    stops whoever reaches a fresh public install first from claiming it. Worthless once any
    account exists."""
    key = get_settings().secret_key.encode()
    digest = hmac.new(key, b"ta-setup-v1", hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")[:32]
