"""EPUB import (spec §6): read the chapter list, then import the chosen chapters
with their illustrations into a series volume. Synchronous (plan ruling 5); the file
is uploaded twice, once per step (ruling 6)."""

import io
import mimetypes
import zipfile
import zlib

from fastapi import Depends, File, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from api.core.epub_build import build_epub
from api.core.epub_read import EpubError, extract_chapter_content, open_book
from api.core.epub_safety import MAX_UNCOMPRESSED, EpubBudgetExceeded, charge
from api.core.text import (
    build_epub_content,
    build_new_file,
    calculate_progress,
    line_has_content,
    lines_to_db_rows,
    parse_file_content,
    sanitize_filename,
)
from api.deps import current_user, db_session, owned_ref, scoped_volume
from api.library import (
    arrange,
    check_line_count,
    line_arrays,
    next_series_order,
    reject_nul,
    write_lines,
)
from api.models import Document, DocumentImage, Series, User, Volume
from api.routers.transfer import attachment
from api.routing import api_router
from api.schemas.epub import BookOut, ChapterError, EpubImportOut
from api.uploads import read_capped

router = api_router(tags=["epub"])

MAX_EPUB_BYTES = 64 * 1024 * 1024  # plan ruling 3; Caddy allows the same on /api/epub/*
# Starlette's multipart max_fields is 1000 and counts the other form fields too.
MAX_CHAPTERS = 900


def _over_budget() -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"EPUB chapters and images exceed {MAX_UNCOMPRESSED // (1024 * 1024)} MB in total; "
        "import fewer chapters at a time",
    )


def _unprocessable(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail)


def _book(file: UploadFile) -> tuple[io.BytesIO, dict]:
    data = io.BytesIO(read_capped(file, MAX_EPUB_BYTES))
    try:
        return data, open_book(data)
    except (EpubError, ValueError, KeyError) as exc:  # ValueError covers bad UTF-8
        raise _unprocessable(f"not a readable EPUB: {exc}") from None


@router.post("/epub/inspect", response_model=BookOut)
def inspect(file: UploadFile = File(...), user: User = Depends(current_user)) -> BookOut:
    _, book = _book(file)
    return BookOut(
        title=book["title"], author=book["author"], illustrator=book["illustrator"],
        publisher=book["publisher"], identifier=book["identifier"],
        has_cover=bool(book["cover_href"]), chapters=book["chapters"],
    )


def _series(db: Session, user: User, series_id: int | None, title: str) -> Series:
    if series_id is not None:
        return owned_ref(db, Series, series_id, user.id, "series_id")
    series = db.scalar(select(Series).where(Series.user_id == user.id, Series.title == title))
    if series is None:
        series = Series(user_id=user.id, title=title)
        db.add(series)
        db.flush()
    return series


def _volume(db: Session, series: Series, title: str, meta: dict[str, str]) -> Volume:
    volume = db.scalar(select(Volume).where(Volume.series_id == series.id, Volume.title == title))
    if volume is None:
        order = db.scalar(
            select(func.coalesce(func.max(Volume.volume_order), 0) + 1).where(
                Volume.series_id == series.id
            )
        )
        volume = Volume(series_id=series.id, title=title, volume_order=order)
        db.add(volume)
    for field, value in meta.items():
        if value.strip():
            setattr(volume, field, value.strip())
    db.flush()
    return volume


def _import_chapter(
    db: Session, user: User, series: Series, volume: Volume, data: io.BytesIO,
    title: str, href: str, order: int, budget: list[int],
) -> tuple[Document, bool]:
    """One chapter into one document; the caller wraps this in a savepoint."""
    # The chapter file is decompressed again for every chapter, so it counts too.
    charge(budget, zipfile.ZipFile(data).getinfo(href).file_size)
    # Images are charged per reference (each is a stored row) before they are read.
    text, images = extract_chapter_content(data, href, budget)
    text = text.replace("\x00", "")  # Postgres text cannot hold NUL
    raw, translated, _ = parse_file_content(build_new_file(text))
    check_line_count(raw)
    doc = Document(
        user_id=user.id, series_id=series.id, volume_id=volume.id,
        title=title, chapter_title=title, series_order=order,
    )
    db.add(doc)
    db.flush()
    write_lines(db, doc.id, lines_to_db_rows(raw, translated))
    db.add_all(
        DocumentImage(
            document_id=doc.id, anchor_position=img["anchor_position"], is_cover=False,
            src_path=img["src_path"], data=img["data"],
        )
        for img in images
    )
    db.flush()
    return doc, not raw


@router.post("/epub/import", response_model=EpubImportOut, status_code=status.HTTP_201_CREATED)
def import_epub(
    file: UploadFile = File(...),
    series_id: int | None = Form(None),
    series_title: str = Form("", max_length=300),
    volume_title: str = Form(..., max_length=300),
    author: str = Form("", max_length=300),
    illustrator: str = Form("", max_length=300),
    publisher: str = Form("", max_length=300),
    identifier: str = Form("", max_length=300),
    hrefs: list[str] = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> EpubImportOut:
    reject_nul(series_title, volume_title, author, illustrator, publisher, identifier)
    if (series_id is None) == (not series_title.strip()):
        raise _unprocessable("give exactly one of series_id and series_title")
    if not volume_title.strip():
        raise _unprocessable("volume_title is required")
    if not 1 <= len(hrefs) <= MAX_CHAPTERS:
        raise _unprocessable(f"choose between 1 and {MAX_CHAPTERS} chapters")

    data, book = _book(file)
    series = _series(db, user, series_id, series_title.strip())
    volume = _volume(db, series, volume_title.strip(), {
        "epub_author": author, "epub_illustrator": illustrator,
        "epub_publisher": publisher, "epub_identifier": identifier,
    })
    already = set(db.scalars(select(Document.chapter_title).where(Document.volume_id == volume.id)))
    known = {c["href"]: c for c in book["chapters"]}

    imported: list[str] = []
    skipped: list[str] = []
    empty: list[str] = []
    errors: list[ChapterError] = []
    first_doc: Document | None = None
    budget = [MAX_UNCOMPRESSED]  # chapter-file + image bytes left for this import
    order = next_series_order(db, series.id)
    for href in hrefs:
        chapter = known.get(href)
        if chapter is None:
            errors.append(ChapterError(title=href, message="not a chapter of this EPUB"))
            continue
        title = chapter["title"]
        if title in already:
            skipped.append(title)
            continue
        try:
            with db.begin_nested():
                doc, is_empty = _import_chapter(
                    db, user, series, volume, data, title, href, order, budget)
        except EpubBudgetExceeded:  # not per chapter: the whole import rolls back
            raise _over_budget() from None
        except (EpubError, ValueError, KeyError, DataError, HTTPException) as exc:
            errors.append(ChapterError(
                title=title, message=str(getattr(exc, "detail", None) or exc)))
            continue
        first_doc = first_doc or doc
        order += 1
        imported.append(title)
        if is_empty:
            empty.append(title)

    cover_href = book["cover_href"]
    if cover_href and first_doc is not None and not db.scalar(
        select(DocumentImage.id)
        .join(Document, Document.id == DocumentImage.document_id)
        .where(Document.volume_id == volume.id, DocumentImage.is_cover.is_(True))
        .limit(1)
    ):
        try:
            cover = zipfile.ZipFile(data).read(cover_href)
        except (zipfile.BadZipFile, KeyError, ValueError, RuntimeError, NotImplementedError,
                EOFError, zlib.error):
            cover = None
        if cover:
            budget[0] -= len(cover)
            if budget[0] < 0:
                raise _over_budget()
            db.add(DocumentImage(
                document_id=first_doc.id, anchor_position=0, is_cover=True,
                src_path=cover_href, data=cover,
            ))
    db.flush()
    arrange(db, series)  # chapters added to an earlier volume move ahead of later ones
    db.flush()
    return EpubImportOut(
        series_id=series.id, volume_id=volume.id, imported=imported, skipped=skipped,
        empty=empty, errors=errors,
    )


@router.get("/volumes/{volume_id}/export/epub")
def export_volume(
    volume_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Response:
    # ponytail: synchronous build, book in memory; make it a job if volumes outgrow a request
    volume = scoped_volume(db, volume_id, user.id)
    docs = db.scalars(select(Document).where(Document.volume_id == volume.id)
                      .order_by(Document.series_order, Document.id))
    chapters, cover, incomplete = [], None, []
    for doc in docs:
        raw, translated = line_arrays(db, doc.id)
        images = list(db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc.id)
                                 .order_by(DocumentImage.anchor_position, DocumentImage.id)))
        inline = [im for im in images if not im.is_cover and not im.exclude_export]
        if cover is None:
            row = next((im for im in images if im.is_cover), None)
            if row is not None:
                media = mimetypes.guess_type(row.src_path)[0] or "application/octet-stream"
                cover = {"data": row.data, "media_type": media}
        has_text = any(line_has_content(r) for r in raw)
        if not has_text and not inline:
            continue  # nothing to show; it must not block the volume (desktop)
        if has_text and calculate_progress(raw, translated)[0] < 100:
            incomplete.append(doc.chapter_title or doc.title)
            continue
        refs = [{"anchor_position": im.anchor_position, "src_path": im.src_path} for im in inline]
        chapters.append((
            doc.chapter_title or doc.title,
            build_epub_content(raw, translated, refs),
            [{"src_path": im.src_path, "data": im.data} for im in inline],
        ))
    if incomplete:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "not fully translated: " + ", ".join(incomplete))
    if not chapters:
        raise _unprocessable("the volume has no chapters with content")
    data = build_epub(
        volume.epub_title or volume.title or volume.series.title, chapters,
        language=volume.epub_language or "en", cover=cover,
        creator=volume.epub_author, illustrator=volume.epub_illustrator,
        publisher=volume.epub_publisher, identifier=volume.epub_identifier,
    )
    name = f"{sanitize_filename(volume.title) or 'volume'}.epub"
    return Response(data, media_type="application/epub+zip", headers=attachment(name))
