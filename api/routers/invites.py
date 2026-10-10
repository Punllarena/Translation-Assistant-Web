from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import db_session, require_admin
from api.models import Invite, User
from api.schemas.invites import InviteCreate, InviteCreated, InviteOut
from api.security import new_token, token_hash

router = APIRouter(prefix="/invites", tags=["invites"])


@router.post("", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
def create_invite(
    body: InviteCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(db_session),
) -> InviteCreated:
    token = new_token()
    expires_at = datetime.now(UTC) + timedelta(days=body.ttl_days)
    email = body.email.strip().lower() if body.email else None
    db.add(
        Invite(
            token_hash=token_hash(token),
            email=email,
            created_by=admin.id,
            expires_at=expires_at,
        )
    )
    db.flush()
    return InviteCreated(token=token, expires_at=expires_at)


@router.get("", response_model=list[InviteOut])
def list_invites(
    admin: User = Depends(require_admin), db: Session = Depends(db_session)
) -> list[Invite]:
    return list(db.scalars(select(Invite).order_by(Invite.created_at.desc())))
