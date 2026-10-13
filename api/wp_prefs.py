"""Per-user WordPress preferences: the desktop's WP* QSettings (dlg_wp_settings.py) as
user_settings keys, with the desktop defaults. A value of the wrong shape reads as its
default, so a bad PUT /settings can never break a publish."""

import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.models import UserSetting

KEYS = ("wp_password_enabled", "wp_unlock_after", "wp_attribution_enabled",
        "wp_default_schedule_time", "wp_chapters_per_day", "wp_schedule_scope_global")
_TIME = re.compile(r"([01]\d|2[0-3]):[0-5]\d")


@dataclass(frozen=True)
class WpPrefs:
    wp_password_enabled: bool
    wp_unlock_after: int
    wp_attribution_enabled: bool
    wp_default_schedule_time: str  # "HH:MM", or "" for none
    wp_chapters_per_day: int
    wp_schedule_scope_global: bool


def _bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int(value: Any, default: int) -> int:
    ok = isinstance(value, int) and not isinstance(value, bool) and 1 <= value <= 99
    return value if ok else default  # the desktop spin boxes' range


def parse(stored: dict[str, Any]) -> WpPrefs:
    t = stored.get("wp_default_schedule_time")
    return WpPrefs(
        wp_password_enabled=_bool(stored.get("wp_password_enabled"), False),
        wp_unlock_after=_int(stored.get("wp_unlock_after"), 3),
        wp_attribution_enabled=_bool(stored.get("wp_attribution_enabled"), True),
        wp_default_schedule_time=t if isinstance(t, str) and _TIME.fullmatch(t) else "",
        wp_chapters_per_day=_int(stored.get("wp_chapters_per_day"), 1),
        wp_schedule_scope_global=_bool(stored.get("wp_schedule_scope_global"), False),
    )


def load(db: Session, user_id: int) -> WpPrefs:
    rows = db.scalars(select(UserSetting).where(
        UserSetting.user_id == user_id, UserSetting.key.in_(KEYS)))
    return parse({r.key: r.value_json for r in rows})
