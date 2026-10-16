"""First-run setup (spec §3): open to anyone until the first account exists."""

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from api.accounts import AlreadySetUp, claim_first_admin, needs_setup, start_session
from api.deps import db_session
from api.models import User
from api.routing import api_router
from api.schemas.auth import UserOut
from api.schemas.setup import SetupAdmin, SetupStatus

router = api_router(prefix="/setup", tags=["setup"])


@router.get("/status", response_model=SetupStatus)
def setup_status(db: Session = Depends(db_session)) -> SetupStatus:
    return SetupStatus(needs_setup=needs_setup(db))


@router.post("/admin", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def claim_admin(body: SetupAdmin, response: Response, db: Session = Depends(db_session)) -> User:
    try:
        user = claim_first_admin(db, body.email, body.password)
    except AlreadySetUp:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Setup is already complete; sign in instead."
        ) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    start_session(db, response, user)
    return user
