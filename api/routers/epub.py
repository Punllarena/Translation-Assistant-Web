"""EPUB import (spec §6): read the chapter list, then import the chosen chapters
with their illustrations into a series volume. Synchronous (plan ruling 5); the file
is uploaded twice, once per step (ruling 6)."""

import io
import zipfile
import zlib

from fastapi import Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from api.core.epub_read import (
    MAX_UNCOMPRESSED,
    EpubError,
    extract_chapter_content,
    open_book,
)
from api.core.text import build_new_file, lines_to_db_rows, parse_file_content
from api.deps import current_user, db_session, owned_ref
from api.library import check_line_count, next_series_order, write_lines
from api.models import Document, DocumentImage, Series, User, Volume
from api.routing import api_router
from api.schemas.epub import BookOut, ChapterError, EpubImportOut
from api.uploads import read_capped

router = api_router(tags=["epub"])

MAX_EPUB_BYTES = 64 * 1024 * 1024  # plan ruling 3; Caddy allows the same on /api/epub/*
# Starlette's multipart max_fields is 1000 and counts the other form fields too.
MAX_CHAPTERS = 900


class _ImageBudgetExceeded(Exception):
    """Not caught per chapter: the whole import rolls back."""


def _over_budget() -> HTTPException:
    return HTTPException(
        status.HTTP_413_CONTENT_TOO_LARGE,
        f"EPUB images exceed {MAX_UNCOMPRESSED // (1024 * 1024)} MB in total; "
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
    text, images = extract_chapter_content(data, href)
    budget[0] -= sum(len(img["data"]) for img in images)
    if budget[0] < 0:
        raise _ImageBudgetExceeded
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
    series_title: str = Form(""),
    volume_title: str = Form(...),
    author: str = Form(""),
    illustrator: str = Form(""),
    publisher: str = Form(""),
    identifier: str = Form(""),
    hrefs: list[str] = Form(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> EpubImportOut:
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
    budget = [MAX_UNCOMPRESSED]  # extracted image bytes left for this whole import
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
        except _ImageBudgetExceeded:
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
    return EpubImportOut(
        series_id=series.id, volume_id=volume.id, imported=imported, skipped=skipped,
        empty=empty, errors=errors,
    )
