"""ZIP downloads: a series or one volume as Markdown, or a chosen set of chapters."""

import io
import zipfile
from collections.abc import Iterable
from typing import Literal

from fastapi import Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.core.text import (
    build_markdown_ruby,
    build_markdown_translation,
    calculate_progress,
    sanitize_filename,
)
from api.deps import current_user, db_session, scoped
from api.library import chapters, line_arrays
from api.models import Document, Series, User, Volume
from api.routers.transfer import attachment, txt_body
from api.routing import api_router
from api.schemas.transfer import ExportZipRequest

router = api_router(tags=["transfer"])


def _zip(entries: Iterable[tuple[Document, str, str]]) -> bytes:
    """ZIP of ``(document, extension, body)`` entries named ``NNN - title.ext``."""
    # ponytail: built in memory; stream it if an export outgrows a few MB
    buf = io.BytesIO()
    names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc, ext, body in entries:
            stem = sanitize_filename(doc.title) or f"doc_{doc.id}"
            name = f"{doc.series_order:03d} - {stem}.{ext}"
            if name in names:  # a duplicate entry would shadow the first in most unzippers
                name = f"{doc.series_order:03d} - {stem} ({doc.id}).{ext}"
            names.add(name)
            zf.writestr(name, body)
    return buf.getvalue()


@router.get("/series/{series_id}/export/markdown")
def export_series_markdown(
    series_id: int,
    variant: Literal["plain", "ruby"] = "plain",
    volume_id: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Response:
    """Every fully translated chapter (of one volume, with ``volume_id``) as
    ``NNN - title.md`` in one ZIP (the desktop wrote a folder). Incomplete chapters are
    skipped, as the desktop does; the count is in the X-TA-Skipped-Incomplete header."""
    series = scoped(db, Series, series_id, user.id)
    label = series.title
    docs = chapters(db, series.id)
    if volume_id is not None:
        volume = db.scalar(
            select(Volume).where(Volume.id == volume_id, Volume.series_id == series.id)
        )
        if volume is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        label = volume.full_title
        docs = [d for d in docs if d.volume_id == volume.id]
    build = build_markdown_ruby if variant == "ruby" else build_markdown_translation
    skipped = 0
    entries = []
    for doc in docs:
        raw, translated = line_arrays(db, doc.id)
        if calculate_progress(raw, translated)[0] < 100:
            skipped += 1
            continue
        entries.append((doc, "md", build(raw, translated, doc.chapter_title or doc.title)))
    folder = sanitize_filename(label) or "series"
    headers = attachment(f"{folder}.zip") | {"X-TA-Skipped-Incomplete": str(skipped)}
    return Response(_zip(entries), media_type="application/zip", headers=headers)


@router.post("/documents/export/zip")
def export_selection_zip(
    body: ExportZipRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Response:
    """The chosen chapters in one ZIP, in series reading order; nothing is skipped."""
    wanted = set(body.document_ids)
    docs = list(
        db.scalars(
            select(Document)
            .where(Document.id.in_(wanted), Document.user_id == user.id)
            .order_by(Document.series_id, Document.series_order, Document.id)
        )
    )
    if len(docs) != len(wanted):  # the ids are in the body: missing and foreign look the same
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "document_ids: no such item")
    build = build_markdown_ruby if body.format == "md-ruby" else build_markdown_translation
    entries = []
    for doc in docs:
        raw, translated = line_arrays(db, doc.id)
        if body.format == "txt":
            entries.append((doc, "txt", txt_body(raw, translated)))
        else:
            entries.append((doc, "md", build(raw, translated, doc.chapter_title or doc.title)))
    return Response(_zip(entries), media_type="application/zip", headers=attachment("chapters.zip"))
