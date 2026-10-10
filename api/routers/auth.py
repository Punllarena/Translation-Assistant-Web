from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.config import get_settings
from api.deps import COOKIE_NAME, current_user, db_session
from api.models import Invite, Profile, User
from api.models import Session as SessionRow
from api.schemas.auth import LoginRequest, UserOut
from api.schemas.invites import AcceptInvite
from api.security import (
    address_limiter,
    email_limiter,
    hash_password,
    new_token,
    token_hash,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# Verified against when no account matches, so unknown-email and wrong-password
# logins both pay one argon2id verification (no timing oracle for account existence).
_DUMMY_HASH = hash_password("dummy-password-for-timing-equalisation")


def _rate_keys(request: Request, email: str) -> tuple[str, str]:
    # Address bucket plus per-account bucket. Never derive these from client-supplied
    # headers (X-Forwarded-For): the attacker would choose their own bucket. Behind a
    # reverse proxy, run uvicorn with --proxy-headers (and a trusted --forwarded-allow-ips)
    # or request.client.host will be the proxy's address for everyone (Task 11 / Caddy).
    host = request.client.host if request.client else "unknown"
    return host, email


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(db_session),
) -> User:
    email = body.email.strip().lower()
    addr_key, email_key = _rate_keys(request, email)
    if not (address_limiter.check(addr_key) and email_limiter.check(email_key)):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts")

    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        verify_password(body.password, _DUMMY_HASH)
        password_ok = False
    else:
        password_ok = verify_password(body.password, user.password_hash)
    if not password_ok:
        address_limiter.record_failure(addr_key)
        email_limiter.record_failure(email_key)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    settings = get_settings()
    token = new_token()
    db.add(
        SessionRow(
            token_hash=token_hash(token),
            user_id=user.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.session_ttl_days),
        )
    )
    db.flush()
    address_limiter.reset(addr_key)
    email_limiter.reset(email_key)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_ttl_days * 86400,
        path="/",
    )
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, db: Session = Depends(db_session)) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if token:
        row = db.scalar(select(SessionRow).where(SessionRow.token_hash == token_hash(token)))
        if row is not None:
            db.delete(row)
            db.flush()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


_INVITE_REJECTED = "invite is invalid or already used"


@router.post("/accept-invite", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def accept_invite(body: AcceptInvite, db: Session = Depends(db_session)) -> User:
    email = body.email.strip().lower()
    invite = db.scalar(select(Invite).where(Invite.token_hash == token_hash(body.token)))
    now = datetime.now(UTC)
    # Every rejection (including a taken email) shares one message so callers cannot
    # probe which tokens or accounts exist.
    if invite is None or invite.accepted_at is not None or invite.expires_at <= now:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _INVITE_REJECTED)
    if invite.email is not None and invite.email.strip().lower() != email:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _INVITE_REJECTED)
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, _INVITE_REJECTED)

    user = User(email=email, password_hash=hash_password(body.password), is_admin=False)
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    invite.accepted_at = now
    db.flush()
    return user
