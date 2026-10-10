"""File-shaped operations: TXT import and the TXT / Markdown downloads that replace the
desktop's save dialogs."""

import io
import zipfile
from pathlib import PureWindowsPath
from typing import Literal
from urllib.parse import quote

from fastapi import Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from api.core.text import (
    SEPARATOR,
    build_markdown_ruby,
    build_markdown_translation,
    calculate_progress,
    lines_to_db_rows,
    parse_file_content,
    sanitize_filename,
)
from api.deps import current_user, db_session, owned_ref, scoped
from api.library import (
    chapters,
    check_line_count,
    line_arrays,
    next_series_order,
    write_lines,
)
from api.models import Document, Series, User
from api.routing import api_router
from api.schemas.documents import DocumentOut
from api.uploads import read_capped

router = api_router(tags=["transfer"])

MAX_TEXT_BYTES = 5 * 1024 * 1024


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def attachment(filename: str) -> dict[str, str]:
    """Content-Disposition for a download: an ASCII fallback plus the RFC 5987 UTF-8
    name. Header values must be latin-1, so a Japanese title written raw would 500."""
    fallback = (
        filename.encode("ascii", "replace").decode("ascii").replace("?", "_").replace('"', "_")
    )
    return {
        "Content-Disposition": (
            f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"
        )
    }


@router.post(
    "/documents/import/txt", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
def import_txt(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    series_id: int | None = Form(None),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Document:
    """A desktop ---SEPERATOR--- file becomes a document (the desktop import_txt). The
    title defaults to the file name without its extension."""
    data = read_capped(file, MAX_TEXT_BYTES)
    if b"\x00" in data:
        raise _unprocessable("not a text file")
    try:
        text = data.decode("utf-8-sig")  # -sig: Windows editors prepend a BOM
    except UnicodeDecodeError:
        raise _unprocessable("file is not UTF-8 text") from None
    try:
        raw, translated, _ = parse_file_content(text)
    except ValueError as exc:
        raise _unprocessable(str(exc)) from None
    check_line_count(raw)
    if series_id is not None:
        owned_ref(db, Series, series_id, user.id, "series_id")
    name = (title or "").strip() or PureWindowsPath(file.filename or "").stem or "Untitled"
    doc = Document(
        user_id=user.id,
        title=name,
        series_id=series_id,
        series_order=next_series_order(db, series_id),
    )
    db.add(doc)
    db.flush()
    write_lines(db, doc.id, lines_to_db_rows(raw, translated))
    return doc


@router.get("/documents/{document_id}/export")
def export_document(
    document_id: int,
    fmt: Literal["txt", "md", "md-ruby"] = Query("txt", alias="format"),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Response:
    doc = scoped(db, Document, document_id, user.id)
    raw, translated = line_arrays(db, doc.id)
    stem = sanitize_filename(doc.title) or f"document-{doc.id}"
    if fmt == "txt":
        # The desktop export_txt layout, which parse_file_content reads back.
        body = "\n".join(raw) + "\n" + SEPARATOR + "\n" + "".join(t + "\n" for t in translated)
        return Response(
            body, media_type="text/plain; charset=utf-8", headers=attachment(f"{stem}.txt")
        )
    build = build_markdown_ruby if fmt == "md-ruby" else build_markdown_translation
    return Response(
        build(raw, translated, doc.chapter_title or doc.title),
        media_type="text/markdown; charset=utf-8",
        headers=attachment(f"{stem}.md"),
    )


@router.get("/series/{series_id}/export/markdown")
def export_series_markdown(
    series_id: int,
    variant: Literal["plain", "ruby"] = "plain",
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Response:
    """Every fully translated chapter as ``NNN - title.md`` in one ZIP (the desktop
    wrote a folder). Incomplete chapters are skipped, as the desktop does; the count
    is in the X-TA-Skipped-Incomplete header."""
    # ponytail: built in memory; stream it if a series' Markdown outgrows a few MB
    series = scoped(db, Series, series_id, user.id)
    build = build_markdown_ruby if variant == "ruby" else build_markdown_translation
    buf = io.BytesIO()
    skipped = 0
    names: set[str] = set()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for doc in chapters(db, series.id):
            raw, translated = line_arrays(db, doc.id)
            if calculate_progress(raw, translated)[0] < 100:
                skipped += 1
                continue
            stem = sanitize_filename(doc.title) or f"doc_{doc.id}"
            name = f"{doc.series_order:03d} - {stem}.md"
            if name in names:  # a duplicate entry would shadow the first in most unzippers
                name = f"{doc.series_order:03d} - {stem} ({doc.id}).md"
            names.add(name)
            zf.writestr(name, build(raw, translated, doc.chapter_title or doc.title))
    folder = sanitize_filename(series.title) or "series"
    headers = attachment(f"{folder}.zip") | {"X-TA-Skipped-Incomplete": str(skipped)}
    return Response(buf.getvalue(), media_type="application/zip", headers=headers)
