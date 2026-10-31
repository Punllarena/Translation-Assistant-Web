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

VIEWS = ("shelf", "list")
BAD_VIEW = "library_view must be shelf or list"

SORT_KEYS = (
    "modified", "syosetu", "added", "title", "progress", "published", "chapters",
)
SORT_DIRS = ("asc", "desc")
BAD_SORT = "library_sort needs key and dir, and no other keys"

FILTER_KEYS = ("sources", "statuses", "wordpress", "archived")
FILTER_SOURCES = ("syosetu", "epub", "other")
FILTER_STATUSES = ("ongoing", "on_hold", "dropped", "completed")
FILTER_WORDPRESS = ("any", "published", "none")
FILTER_ARCHIVED = ("hide", "include", "only")
BAD_FILTERS = (
    "library_filters needs sources, statuses, wordpress and archived, and no other keys"
)


def _known_list(value: Any, known: tuple[str, ...]) -> bool:
    return isinstance(value, list) and all(
        isinstance(item, str) and item in known for item in value
    )


def _check_sort(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"key", "dir"}
        and value["key"] in SORT_KEYS
        and value["dir"] in SORT_DIRS
    )


def _check_filters(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == set(FILTER_KEYS)
        and _known_list(value["sources"], FILTER_SOURCES)
        and _known_list(value["statuses"], FILTER_STATUSES)
        and value["wordpress"] in FILTER_WORDPRESS
        and value["archived"] in FILTER_ARCHIVED
    )


def check(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if key == "ollama_think":
        return None if isinstance(value, bool) else "ollama_think must be true or false"
    if key == schedule.KEY:
        return None if schedule.parse(value) is not None else BAD_SCHEDULE
    if key == "series_columns":
        ok = isinstance(value, list) and all(
            isinstance(item, str) and item in SERIES_COLUMNS for item in value
        )
        return None if ok else BAD_COLUMNS
    if key == "library_view":
        return None if value in VIEWS and isinstance(value, str) else BAD_VIEW
    if key == "library_sort":
        return None if _check_sort(value) else BAD_SORT
    if key == "library_filters":
        return None if _check_filters(value) else BAD_FILTERS
    return None
