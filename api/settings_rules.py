"""Per-key rules for ``PUT /settings``: a malformed value is a 422 rather than a setting the
reader can never use. ``check`` returns the message, or None when the key is unconstrained
(or the value is null, which clears it)."""

from typing import Any

from api.ollama import schedule

BAD_SCHEDULE = (
    "ollama_schedule needs enabled, start and end (HH:MM), days (0-6) "
    "and a known time zone"
)

SERIES_COLUMNS = (
    "num", "title", "progress", "edited", "wp", "original", "images", "lines", "translated",
    "chars", "words", "wp_date", "ollama", "source", "added",
)
BAD_COLUMNS = "series_columns must be a list of known column ids"


def check(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if key == schedule.KEY:
        return None if schedule.parse(value) is not None else BAD_SCHEDULE
    if key == "series_columns":
        ok = isinstance(value, list) and all(
            isinstance(item, str) and item in SERIES_COLUMNS for item in value
        )
        return None if ok else BAD_COLUMNS
    return None
