from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import db_session, require_admin
from api.models import Invite, User
from api.routing import api_router
from api.schemas.invites import InviteCreate, InviteCreated, InviteOut
from api.security import new_token, token_hash

router = api_router(prefix="/invites", tags=["invites"])


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


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: int, _: User = Depends(require_admin), db: Session = Depends(db_session)
) -> None:
    invite = db.get(Invite, invite_id)
    if invite is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "this invite was already used")
    db.delete(invite)
    db.flush()
