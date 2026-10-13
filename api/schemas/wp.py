from pydantic import BaseModel


class WpPrefsOut(BaseModel):
    wp_password_enabled: bool
    wp_unlock_after: int
    wp_attribution_enabled: bool
    wp_default_schedule_time: str
    wp_chapters_per_day: int
    wp_schedule_scope_global: bool


class WpTestOut(BaseModel):
    ok: bool
    message: str
