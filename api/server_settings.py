"""Server-wide settings an admin edits in the browser (spec §4). Value = DB row, else the
env var of the same name (api/config.py), else its code default. No cache: one small query."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from api.config import get_settings
from api.models import ServerSetting


def _url(key, v):
    if not isinstance(v, str):
        raise ValueError(f"{key} must be text")
    v = v.strip()
    parts = urlsplit(v)
    if v and (parts.scheme not in ("http", "https") or not parts.netloc):
        raise ValueError(f"{key} must be an http:// or https:// address")
    return v


def _bool(key, v):
    if not isinstance(v, bool):
        raise ValueError(f"{key} must be true or false")
    return v


def _delay(key, v):
    if isinstance(v, bool) or not isinstance(v, int | float) or not 1 <= v <= 60:
        raise ValueError(f"{key} must be a number of seconds from 1 to 60")
    return float(v)


VALIDATORS = {
    "ollama_url": _url,
    "libretranslate_url": _url,
    "mt_allow_private_urls": _bool,
    "wp_allow_private_urls": _bool,
    "syosetu_delay_seconds": _delay,
}
KEYS = tuple(VALIDATORS)


@dataclass(frozen=True)
class ServerPrefs:
    ollama_url: str
    libretranslate_url: str
    mt_allow_private_urls: bool
    wp_allow_private_urls: bool
    syosetu_delay_seconds: float


def validate(key: str, value):
    """The cleaned value; KeyError for an unknown key, ValueError for a bad value."""
    return VALIDATORS[key](key, value)


def _rows(db: Session) -> dict:
    return dict(db.execute(select(ServerSetting.key, ServerSetting.value)).all())


def effective(db: Session) -> ServerPrefs:
    rows, env = _rows(db), get_settings()
    return ServerPrefs(**{k: rows[k] if k in rows else getattr(env, k) for k in KEYS})


def _entry(key: str, rows: dict) -> dict:
    env = get_settings()
    if key in rows:
        return {"key": key, "value": rows[key], "source": "db"}
    # pydantic-settings records env-sourced fields in model_fields_set
    source = "env" if key in env.model_fields_set else "default"
    return {"key": key, "value": getattr(env, key), "source": source}


def listing(db: Session) -> list[dict]:
    rows = _rows(db)
    return [_entry(k, rows) for k in KEYS]


def put(db: Session, key: str, value, user_id: int) -> dict:
    value = validate(key, value)
    stmt = insert(ServerSetting).values(key=key, value=value, updated_by=user_id)
    db.execute(stmt.on_conflict_do_update(
        index_elements=[ServerSetting.key],
        set_={"value": stmt.excluded.value, "updated_by": user_id, "updated_at": func.now()},
    ))
    db.flush()
    return _entry(key, {key: value})


def reset(db: Session, key: str) -> None:
    if key not in VALIDATORS:
        raise KeyError(key)
    db.execute(delete(ServerSetting).where(ServerSetting.key == key))
    db.flush()
