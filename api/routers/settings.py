from fastapi import Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from api.deps import current_user, db_session
from api.models import Shortcut, User, UserSetting
from api.routing import api_router
from api.schemas.settings import SettingsMap, ShortcutsMap

router = api_router(tags=["settings"])


def _load_settings(db: Session, user_id: int) -> SettingsMap:
    rows = db.scalars(select(UserSetting).where(UserSetting.user_id == user_id))
    return {r.key: r.value_json for r in rows}


def _load_shortcuts(db: Session, user_id: int) -> ShortcutsMap:
    rows = db.scalars(select(Shortcut).where(Shortcut.user_id == user_id))
    return {r.action_key: r.binding for r in rows}


@router.get("/settings", response_model=SettingsMap)
def list_settings(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> SettingsMap:
    return _load_settings(db, user.id)


@router.put("/settings", response_model=SettingsMap)
def put_settings(
    body: SettingsMap, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> SettingsMap:
    existing = {
        r.key: r for r in db.scalars(select(UserSetting).where(UserSetting.user_id == user.id))
    }
    for key, value in body.items():
        if key in existing:
            existing[key].value_json = value
        else:
            db.add(UserSetting(user_id=user.id, key=key, value_json=value))
    db.flush()
    return _load_settings(db, user.id)


@router.delete("/settings/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_setting(
    key: str, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.execute(delete(UserSetting).where(UserSetting.user_id == user.id, UserSetting.key == key))
    db.flush()


@router.get("/shortcuts", response_model=ShortcutsMap)
def list_shortcuts(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> ShortcutsMap:
    return _load_shortcuts(db, user.id)


@router.put("/shortcuts", response_model=ShortcutsMap)
def put_shortcuts(
    body: ShortcutsMap, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> ShortcutsMap:
    rows = {
        r.action_key: r for r in db.scalars(select(Shortcut).where(Shortcut.user_id == user.id))
    }
    # Check the merged state, so a new action colliding with a stored binding is caught.
    merged = {action: r.binding for action, r in rows.items()} | body
    owner_of: dict[str, str] = {}
    for action, binding in merged.items():
        if binding in owner_of:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"{binding} is already bound to {owner_of[binding]}",
            )
        owner_of[binding] = action
    for action, binding in body.items():
        if action in rows:
            rows[action].binding = binding
        else:
            db.add(Shortcut(user_id=user.id, action_key=action, binding=binding))
    db.flush()
    return _load_shortcuts(db, user.id)


@router.delete("/shortcuts/{action_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shortcut(
    action_key: str, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.execute(
        delete(Shortcut).where(Shortcut.user_id == user.id, Shortcut.action_key == action_key)
    )
    db.flush()
