import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped
from api.models import ApiCredential, User
from api.schemas.credentials import CredentialCreate, CredentialOut, CredentialUpdate
from api.security import decrypt_secret, encrypt_secret

router = APIRouter(prefix="/credentials", tags=["credentials"])
log = logging.getLogger(__name__)

HINT_MIN_LENGTH = 8
UNIQUE_VIOLATION = "23505"


def _hint(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= HINT_MIN_LENGTH else ""


def _conflict(exc: IntegrityError) -> HTTPException:
    """409 for a unique violation; any other integrity error is re-raised (500)."""
    if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
        raise exc
    return HTTPException(status.HTTP_409_CONFLICT, "that credential already exists")


def _stored_secret(row: ApiCredential) -> str | None:
    """Decrypt a row for its hint. An undecryptable blob (e.g. after a TA_SECRET_KEY
    change) is logged and reported as no secret, so the list still renders and the
    user can re-enter it. The warning keeps the failure visible in the logs."""
    try:
        return decrypt_secret(row.secret_enc)
    except ValueError:
        log.warning("credential %s could not be decrypted; check TA_SECRET_KEY", row.id)
        return None


def _out(row: ApiCredential, secret: str | None) -> CredentialOut:
    return CredentialOut(
        id=row.id,
        kind=row.kind,
        name=row.name,
        endpoint_url=row.endpoint_url,
        has_secret=bool(secret),
        secret_hint=_hint(secret or ""),
    )


def load_secret(db: Session, user_id: int, kind: str, name: str = "") -> str | None:
    """Server-side only. Nothing reachable over HTTP returns this value."""
    row = db.scalar(
        select(ApiCredential).where(
            ApiCredential.user_id == user_id,
            ApiCredential.kind == kind,
            ApiCredential.name == name,
        )
    )
    return None if row is None else decrypt_secret(row.secret_enc)


@router.get("", response_model=list[CredentialOut])
def list_credentials(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[CredentialOut]:
    rows = db.scalars(
        select(ApiCredential)
        .where(ApiCredential.user_id == user.id)
        .order_by(ApiCredential.kind, ApiCredential.name)
    )
    return [_out(row, _stored_secret(row)) for row in rows]


@router.post("", response_model=CredentialOut, status_code=status.HTTP_201_CREATED)
def create_credential(
    body: CredentialCreate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> CredentialOut:
    row = ApiCredential(
        user_id=user.id,
        kind=body.kind,
        name=body.name,
        secret_enc=encrypt_secret(body.secret),
        endpoint_url=body.endpoint_url,
    )
    # SAVEPOINT: a duplicate undoes only this insert, never the rest of the request's work.
    try:
        with db.begin_nested():
            db.add(row)
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return _out(row, body.secret)


@router.patch("/{credential_id}", response_model=CredentialOut)
def update_credential(
    credential_id: int,
    body: CredentialUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> CredentialOut:
    row = scoped(db, ApiCredential, credential_id, user.id)
    data = body.model_dump(exclude_unset=True)
    secret = data.pop("secret", None)  # validator guarantees None here means "omitted"
    try:
        with db.begin_nested():
            if secret is not None:
                row.secret_enc = encrypt_secret(secret)
            for field, value in data.items():
                setattr(row, field, value)
    except IntegrityError as exc:
        raise _conflict(exc) from exc
    return _out(row, secret if secret is not None else _stored_secret(row))


@router.delete("/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(
    credential_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.delete(scoped(db, ApiCredential, credential_id, user.id))
    db.flush()
