"""Where a volume sits among its series' volumes (spec 2026-10-21-volume-naming, Ordering)."""

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.core.volume_names import sort_key
from api.models import Series, Volume


def _volumes(db: Session, series_id: int) -> list[Volume]:
    return list(
        db.scalars(
            select(Volume)
            .where(Volume.series_id == series_id)
            .order_by(Volume.volume_order, Volume.id)
        )
    )


def _number(ordered: list[Volume]) -> None:
    for position, vol in enumerate(ordered, start=1):
        if vol.volume_order != position:
            vol.volume_order = position


def _key(vol: Volume) -> tuple:
    return (sort_key(vol.kind, vol.volume_index), vol.id)


def place(db: Session, volume: Volume) -> None:
    """Position ``volume`` and renumber volume_order 1..N. Siblings (same kind) decide
    first; a lone volume of its kind goes after the last volume that sorts lower.
    The volume must be flushed (it has an id). The caller flushes and runs arrange()."""
    others = [v for v in _volumes(db, volume.series_id) if v.id != volume.id]
    mine = _key(volume)
    kind = volume.kind.strip().casefold()
    siblings = [(i, v) for i, v in enumerate(others) if v.kind.strip().casefold() == kind]
    lower = [i for i, v in siblings if _key(v) < mine]
    higher = [i for i, v in siblings if _key(v) > mine]
    if lower:
        at = max(lower) + 1
    elif higher:
        at = min(higher)
    else:
        below = [i for i, v in enumerate(others) if _key(v)[0] < mine[0]]
        at = max(below) + 1 if below else 0
    others.insert(at, volume)
    _number(others)


def reorder(db: Session, series: Series, ids: list[int]) -> list[Volume]:
    """Apply a drag order; a stale or duplicate list is refused, not half-applied."""
    by_id = {v.id: v for v in _volumes(db, series.id)}
    if sorted(ids) != sorted(by_id):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "volume_ids: list every volume of this series once",
        )
    ordered = [by_id[i] for i in ids]
    _number(ordered)
    return ordered


def sort_by_number(db: Session, series: Series) -> list[Volume]:
    ordered = sorted(_volumes(db, series.id), key=_key)
    _number(ordered)
    return ordered
