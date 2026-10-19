from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.accounts import find_by_username, start_session
from api.deps import COOKIE_NAME, current_user, db_session
from api.models import Invite, Profile, User
from api.models import Session as SessionRow
from api.routing import api_router
from api.schemas.auth import LoginRequest, UserOut
from api.schemas.invites import AcceptInvite
from api.security import (
    account_limiter,
    address_limiter,
    email_limiter,
    hash_password,
    token_hash,
    verify_password,
)

router = api_router(prefix="/auth", tags=["auth"])


# Verified against when no account matches, so unknown-email and wrong-password
# logins both pay one argon2id verification (no timing oracle for account existence).
_DUMMY_HASH = hash_password("dummy-password-for-timing-equalisation")


def _rate_keys(request: Request, account: str) -> tuple[str, str]:
    # Address bucket plus per-account bucket. Never derive these from client-supplied
    # headers (X-Forwarded-For): the attacker would choose their own bucket. Behind a
    # reverse proxy, run uvicorn with --proxy-headers (and a trusted --forwarded-allow-ips)
    # or request.client.host will be the proxy's address for everyone (Task 11 / Caddy).
    host = request.client.host if request.client else "unknown"
    return host, account


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(db_session),
) -> User:
    login = body.login.strip().lower()
    # Keyed by the login string, never by whether it matched an account: a shared per-account
    # 429 would reveal which username and email belong together. account_limiter caps the
    # account itself, silently (below). Every bucket is charged up front, atomically, and
    # cleared on success, so concurrent requests cannot all slip past one check.
    addr_key, email_key = _rate_keys(request, login)
    if not address_limiter.try_acquire(addr_key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts")
    if not email_limiter.try_acquire(email_key):
        address_limiter.release(addr_key)  # a 429 never charges a bucket
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts")

    if "@" in login:
        user = db.scalar(select(User).where(User.email == login))
    else:
        user = find_by_username(db, login)
    # A full account bucket takes no further charge, so guesses cannot extend its window.
    if user is None or not account_limiter.try_acquire(f"user:{user.id}"):
        # Unknown account and exhausted account look the same: one argon2id verify, then 401.
        verify_password(body.password, _DUMMY_HASH)
        password_ok = False
    else:
        password_ok = verify_password(body.password, user.password_hash)
    if not password_ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    start_session(db, response, user)
    address_limiter.reset(addr_key)
    email_limiter.reset(email_key)
    account_limiter.reset(f"user:{user.id}")
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
    rejected = HTTPException(status.HTTP_400_BAD_REQUEST, _INVITE_REJECTED)
    if invite is None or invite.accepted_at is not None or invite.expires_at <= now:
        raise rejected
    if invite.email is not None and invite.email.strip().lower() != email:
        raise rejected
    if db.scalar(select(User).where(User.email == email)) is not None:
        raise rejected
    # Only reached with a live invite, so this does not let strangers probe usernames.
    if find_by_username(db, body.username) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken.")

    user = User(
        email=email, username=body.username,
        password_hash=hash_password(body.password), is_admin=False,
    )
    try:
        # Savepoint: a rejected claim or a lost email race rolls back both, so a failed
        # accept never consumes the invite or leaves a user behind.
        with db.begin_nested():
            # Atomic single-use claim: only one concurrent request flips accepted_at from NULL.
            claimed = db.execute(
                update(Invite)
                .where(Invite.id == invite.id, Invite.accepted_at.is_(None))
                .values(accepted_at=now)
            )
            if claimed.rowcount != 1:
                raise rejected
            db.add(user)
            db.flush()  # only this flush may raise IntegrityError (email/username unique)
    except IntegrityError:
        raise rejected from None
    db.add(Profile(user_id=user.id, name="default", is_default=True))
    db.flush()
    return user
