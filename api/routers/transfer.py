"""File-shaped operations: TXT import and the TXT / Markdown downloads that replace the
desktop's save dialogs."""

import io
import zipfile
from pathlib import PureWindowsPath
from typing import Literal
from urllib.parse import quote

from fastapi import Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.core.text import (
    SEPARATOR,
    build_markdown_ruby,
    build_markdown_translation,
    calculate_progress,
    lines_to_db_rows,
    natural_key,
    parse_file_content,
    sanitize_filename,
)
from api.deps import current_user, db_session, owned_ref, scoped
from api.library import (
    chapters,
    check_line_count,
    line_arrays,
    next_series_order,
    reject_nul,
    write_lines,
)
from api.models import Document, Profile, Series, User
from api.routers.glossary import MAX_CSV_BYTES, import_pairs
from api.routing import api_router
from api.schemas.documents import DocumentOut
from api.schemas.transfer import BatchImportOut
from api.uploads import read_capped

router = api_router(tags=["transfer"])

MAX_TEXT_BYTES = 5 * 1024 * 1024
MAX_BATCH_FILES = 500
MAX_BATCH_BYTES = 12 * 1024 * 1024  # Caddy's body cap, enforced here too


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _txt_lines(data: bytes) -> tuple[list[str], list[str]]:
    """Raw and translated lines of a desktop ---SEPERATOR--- file; 422 when unusable."""
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
    return raw, translated


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
    series_id: int = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Document:
    """A desktop ---SEPERATOR--- file becomes a document (the desktop import_txt). The
    title defaults to the file name without its extension."""
    raw, translated = _txt_lines(read_capped(file, MAX_TEXT_BYTES))
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


def _series_for(db: Session, user: User, series_id: int | None, title: str) -> Series:
    reject_nul(title)
    title = title.strip()
    if series_id is not None and title:
        raise _unprocessable("give series_id or series_title, not both")
    if series_id is not None:
        return owned_ref(db, Series, series_id, user.id, "series_id")
    if not title:
        raise _unprocessable("give series_id or series_title")
    series = db.scalar(select(Series).where(Series.user_id == user.id, Series.title == title))
    if series is None:
        series = Series(user_id=user.id, title=title)
        db.add(series)
        db.flush()
    return series


class _BatchTooLarge(HTTPException):
    pass


class _Budget:
    """Bytes read across one batch; 413 for the whole request once past the cap."""

    def __init__(self) -> None:
        self.total = 0

    def read(self, upload: UploadFile, cap: int) -> bytes:
        data = read_capped(upload, cap)  # a single oversized file is a per-file 413
        self.total += len(data)
        if self.total > MAX_BATCH_BYTES:
            raise _BatchTooLarge(status.HTTP_413_CONTENT_TOO_LARGE, "batch is too large")
        return data


def _batch_glossary(db, user, csv_file, series, errors, budget) -> int | None:
    """Upsert the one CSV into a profile named by its stem; the series adopts it."""
    name = PureWindowsPath(csv_file.filename or "").stem[:120] or "Imported"
    try:
        data = budget.read(csv_file, MAX_CSV_BYTES)
    except _BatchTooLarge:
        raise
    except HTTPException as exc:
        errors.append({"name": csv_file.filename, "message": str(exc.detail)})
        return None
    try:
        with db.begin_nested():
            text = data.decode("utf-8-sig")
            profile = db.scalar(
                select(Profile).where(Profile.user_id == user.id, Profile.name == name)
            )
            if profile is None:
                profile = Profile(user_id=user.id, name=name)
                db.add(profile)
                db.flush()
            import_pairs(db, profile.id, text)
    except UnicodeDecodeError:
        errors.append({"name": csv_file.filename, "message": "file is not UTF-8 text"})
        return None
    except HTTPException as exc:
        errors.append({"name": csv_file.filename, "message": str(exc.detail)})
        return None
    series.profile_id = profile.id
    return profile.id


@router.post(
    "/documents/import/batch", response_model=BatchImportOut, status_code=status.HTTP_201_CREATED
)
def import_batch(
    files: list[UploadFile] = File(...),
    series_id: int | None = Form(None),
    series_title: str = Form("", max_length=300),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> dict:
    """The desktop batch_import_folder: many .txt files become chapters, appended to the
    series in natural filename order; titles already present are skipped. One .csv is
    imported as the series' glossary profile. Bad files are reported, not fatal."""
    if len(files) > MAX_BATCH_FILES:
        raise _unprocessable(f"more than {MAX_BATCH_FILES} files")
    series = _series_for(db, user, series_id, series_title)
    errors: list[dict] = []
    warnings: list[str] = []
    budget = _Budget()
    texts: list[tuple[str, UploadFile]] = []
    csvs: list[UploadFile] = []
    for f in files:
        name = f.filename or ""
        ext = PureWindowsPath(name).suffix.lower()
        if "\x00" in name:
            errors.append({"name": name, "message": "invalid file name"})
        elif ext == ".txt":
            texts.append((PureWindowsPath(name).stem, f))
        elif ext == ".csv":
            csvs.append(f)
        else:
            errors.append({"name": name, "message": "not a .txt or .csv file"})
    profile_id = None
    if len(csvs) == 1:
        profile_id = _batch_glossary(db, user, csvs[0], series, errors, budget)
    elif csvs:
        warnings.append(f"{len(csvs)} CSV files found; glossary import skipped.")
    existing = set(db.scalars(select(Document.title).where(Document.user_id == user.id)))
    first = next_series_order(db, series.id)
    imported: list[str] = []
    skipped: list[str] = []
    for stem, f in sorted(texts, key=lambda t: natural_key(t[0])):
        title = stem or "Untitled"
        if title in existing:
            skipped.append(title)
            continue
        try:
            data = budget.read(f, MAX_TEXT_BYTES)
        except _BatchTooLarge:
            raise
        except HTTPException as exc:
            errors.append({"name": f.filename, "message": str(exc.detail)})
            continue
        try:
            with db.begin_nested():
                raw, translated = _txt_lines(data)
                doc = Document(
                    user_id=user.id,
                    title=title,
                    series_id=series.id,
                    series_order=first + len(imported),
                )
                db.add(doc)
                db.flush()
                write_lines(db, doc.id, lines_to_db_rows(raw, translated))
        except HTTPException as exc:
            errors.append({"name": f.filename, "message": str(exc.detail)})
            continue
        existing.add(title)
        imported.append(title)
    return {
        "series_id": series.id,
        "profile_id": profile_id,
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "warnings": warnings,
    }


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
