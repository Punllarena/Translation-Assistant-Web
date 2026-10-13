from datetime import datetime

from pydantic import AwareDatetime, BaseModel


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


class WpStatusOut(BaseModel):
    cached_status: str  # before the refresh
    status: str  # after it ("" = not on WordPress)
    post_url: str
    remote_error: str  # why WordPress could not be asked; "" when it answered
    previous_scheduled: bool
    suggested_slot: datetime | None


class PublishIn(BaseModel):
    scheduled_for: AwareDatetime | None = None
    confirm_republish: bool = False


class PublishOut(BaseModel):
    created: bool
    updated: bool
    page_url: str
    post_url: str
    password: str | None
    unlock_chapter_index: int | None
    scheduled_for: datetime | None
