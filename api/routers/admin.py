"""Admin-only server settings (spec §4.4)."""

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from api import server_settings
from api.deps import db_session, require_admin
from api.models import User
from api.routing import api_router
from api.schemas.admin import ServerSettingOut, SettingValue

router = api_router(prefix="/admin", tags=["admin"])


def _unknown(key: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"no server setting named {key!r}")


@router.get("/settings", response_model=list[ServerSettingOut])
def list_settings(
    _: User = Depends(require_admin), db: Session = Depends(db_session)
) -> list[dict]:
    return server_settings.listing(db)


@router.put("/settings/{key}", response_model=ServerSettingOut)
def put_setting(key: str, body: SettingValue, admin: User = Depends(require_admin),
                db: Session = Depends(db_session)) -> dict:
    try:
        return server_settings.put(db, key, body.value, admin.id)
    except KeyError:
        raise _unknown(key) from None
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.delete("/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
def reset_setting(key: str, _: User = Depends(require_admin),
                  db: Session = Depends(db_session)) -> None:
    try:
        server_settings.reset(db, key)
    except KeyError:
        raise _unknown(key) from None
