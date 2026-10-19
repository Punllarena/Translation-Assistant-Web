"""First-run setup: the first admin account, created from the browser with the token the
server logs at startup (`api.accounts.setup_token`)."""

import hmac

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.accounts import create_admin, has_users, setup_token
from api.deps import db_session
from api.models import User
from api.routing import api_router
from api.schemas.auth import SetupRequest, SetupStatus, UserOut
from api.security import address_limiter

router = api_router(prefix="/setup", tags=["setup"])

# Any constant: serialises concurrent setup requests so only one can find no users.
_SETUP_LOCK = 0x7A5E7
_ALREADY = "this server is already set up"


@router.get("", response_model=SetupStatus)
def setup_status(db: Session = Depends(db_session)) -> SetupStatus:
    return SetupStatus(needed=not has_users(db))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def run_setup(body: SetupRequest, request: Request, db: Session = Depends(db_session)) -> User:
    addr = f"setup:{request.client.host if request.client else 'unknown'}"
    if not address_limiter.check(addr):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts")
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SETUP_LOCK})
    if has_users(db):
        raise HTTPException(status.HTTP_409_CONFLICT, _ALREADY)
    if not hmac.compare_digest(body.token.encode(), setup_token().encode()):
        address_limiter.record_failure(addr)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "setup token is wrong")
    address_limiter.reset(addr)
    return create_admin(db, body.email, body.password)
