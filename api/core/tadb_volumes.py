"""ta.db volumes: a desktop volume title becomes (kind, number, subtitle)."""

import sqlite3
from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.tadb_schema import VOLUME_META, ImportReport, _get
from api.core.volume_names import parse_title_fit
from api.models import Series, Volume


def _volume_meta(row: sqlite3.Row) -> dict[str, str]:
    return {
        attr: _get(row, "documents", column, "") or "" for attr, column in VOLUME_META.items()
    }


def _merge_volume_meta(volume: Volume, meta: dict[str, str], report: ImportReport) -> None:
    """First non-empty value wins; a later chapter that disagrees is reported."""
    for attr, value in meta.items():
        if not value:
            continue
        current = getattr(volume, attr) or ""
        if not current:
            setattr(volume, attr, value)
        elif current != value:
            report.messages.append(
                f"volumes {volume.label!r}: {attr} kept as {current!r}; another chapter "
                f"says {value!r}"
            )


def find_or_add_volume(
    db: Session, series: Series, title: str, cache: dict[tuple, Volume | str | None],
    report: ImportReport, meta: dict[str, str],
    add: Callable[[Session, object, str, str, ImportReport], bool],  # tadb_rows._add
) -> Volume | None:
    """The volume a desktop title names, found by (kind, number) or (kind, subtitle) and
    created in desktop order (appended, no re-sorting) when new. The cache is keyed by
    the desktop title itself; ("created", volume id) holds the title that created a volume,
    so a second title landing on it ("Vol 3" then "Volume 3") is reported."""
    key = (series.id, title)
    if key not in cache:
        kind, index, subtitle = parse_title_fit(title, series.title)
        volume = db.scalar(
            select(Volume).where(Volume.series_id == series.id, Volume.named(kind, index, subtitle))
        )
        if volume is None:
            order = db.scalar(select(func.count(Volume.id)).where(Volume.series_id == series.id))
            volume = Volume(series_id=series.id, kind=kind, volume_index=index, subtitle=subtitle,
                            volume_order=order or 0, **meta)
            if not add(db, volume, "volumes", repr(title), report):
                volume = None
            else:
                cache[("created", volume.id)] = title
        else:
            first = cache.get(("created", volume.id))
            if first is not None and first != title:
                report.messages.append(
                    f"volumes {title!r}: merged into {volume.label!r}, created from {first!r}"
                )
            _merge_volume_meta(volume, meta, report)
        cache[key] = volume
    elif cache[key] is not None:
        _merge_volume_meta(cache[key], meta, report)
    return cache[key]
