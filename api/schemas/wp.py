from datetime import datetime

from pydantic import AwareDatetime, BaseModel, Field, model_validator


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


class BatchPublishIn(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=500)
    schedule: bool = True  # the desktop dialog's default
    start: AwareDatetime | None = None
    chapters_per_day: int = Field(default=1, ge=1, le=99)
    tz: str = Field(default="UTC", max_length=64)
    confirm_republish: bool = False

    @model_validator(mode="after")
    def _start_when_scheduling(self) -> "BatchPublishIn":
        if self.schedule and self.start is None:
            raise ValueError("start: required when scheduling")
        return self
