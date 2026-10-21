"""Regroup a syosetu series when its heading-volume setting changes (spec 2026-10-21
syosetu heading volumes). Only chapters in No volume or in heading-made volumes move;
volumes are never deleted, so an emptied one is found again when the setting goes back."""

from collections import Counter
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.core.syosetu_volumes import heading_sequence, targets
from api.fetch_job import group_volume
from api.library import arrange
from api.models import Document, Series, VolumeSyosetuGroup


def regroup(
    db: Session, series: Series, mode: str, marker: str, apply: bool,
    read_index: Callable[[], list[dict]],
) -> dict:
    """Preview (``apply=False``: writes only the heading sequence, when none is stored)
    or apply the move. Returns the counts the confirmation shows."""
    if series.syosetu_headings is None:
        series.syosetu_headings = heading_sequence(read_index())
    docs = list(db.scalars(
        select(Document).where(Document.series_id == series.id)
        .order_by(Document.series_order, Document.id)
    ))
    groups = dict(db.execute(
        select(VolumeSyosetuGroup.heading, VolumeSyosetuGroup.volume_id)
        .where(VolumeSyosetuGroup.series_id == series.id)
    ).all())
    made = set(groups.values())
    place = targets(series.syosetu_headings, [d.series_order for d in docs], mode, marker)
    before = Counter(d.volume_id for d in docs if d.volume_id in made)
    after = Counter(before)
    created: set[str] = set()
    moves: list[tuple[Document, str | None]] = []
    for doc in docs:
        if doc.volume_id is not None and doc.volume_id not in made:
            continue  # a hand-made volume: the owner put it there
        heading = place[doc.series_order]
        if heading is not None and heading not in groups:
            created.add(heading)
        elif (groups[heading] if heading is not None else None) == doc.volume_id:
            continue
        moves.append((doc, heading))
        if doc.volume_id is not None:
            after[doc.volume_id] -= 1
        if heading in groups:
            after[groups[heading]] += 1
    counts = {
        "volumes_created": len(created),
        "chapters_moved": len(moves),
        "volumes_emptied": sum(1 for v, n in before.items() if n and not after[v]),
    }
    if apply:
        series.syosetu_volume_mode, series.syosetu_volume_marker = mode, marker
        for doc, heading in moves:
            doc.volume_id = group_volume(db, series.id, heading).id if heading else None
        db.flush()
        arrange(db, series)
        db.flush()
    return counts
