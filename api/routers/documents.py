from fastapi import Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.core.text import build_new_file, lines_to_db_rows, parse_file_content
from api.deps import current_user, db_session, owned_ref, scoped
from api.library import (
    arrange,
    check_line_count,
    next_series_order,
    send_to_volume_end,
    write_lines,
)
from api.models import Document, DocumentImage, Line, Series, User, Volume
from api.restructure import NotOwned, RestructureError, merge_documents, split_document
from api.routing import api_router
from api.schemas.documents import (
    DocumentCreate,
    DocumentListItem,
    DocumentOut,
    DocumentUpdate,
    MergeRequest,
    SplitRequest,
)

router = api_router(prefix="/documents", tags=["documents"])


def progress(line_count: int, translated_count: int, image_count: int) -> int:
    """The desktop list_documents rule; an illustration-only chapter counts as done."""
    if line_count == 0:
        return 100 if image_count else 0
    return translated_count * 100 // line_count


def check_placement(
    db: Session, user_id: int, series_id: int, volume_id: int | None
) -> None:
    """A (series, volume) pair named in a request body must be the caller's and agree."""
    owned_ref(db, Series, series_id, user_id, "series_id")
    if volume_id is None:
        return
    volume = db.get(Volume, volume_id)
    if volume is None or volume.series_id != series_id:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "volume_id: not a volume of that series"
        )


@router.get("", response_model=list[DocumentListItem])
def list_documents(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[DocumentListItem]:
    """Every document the caller owns, most recently edited first; the picker groups
    by series_id and filters client-side."""
    # ponytail: one unpaginated list; page it if a library outgrows a few thousand chapters
    has_text = func.trim(Line.raw_text) != ""
    lines = (
        select(
            Line.document_id,
            func.count().filter(has_text).label("line_count"),
            func.count().filter(has_text, Line.translated_text != "").label("translated_count"),
        )
        .group_by(Line.document_id)
        .subquery()
    )
    images = (
        select(
            DocumentImage.document_id,
            func.count().label("image_count"),
            func.bool_or(DocumentImage.is_cover).label("has_cover"),
            func.min(DocumentImage.id).filter(DocumentImage.is_cover).label("cover_image_id"),
        )
        .group_by(DocumentImage.document_id)
        .subquery()
    )
    rows = db.execute(
        select(
            Document,
            func.coalesce(lines.c.line_count, 0),
            func.coalesce(lines.c.translated_count, 0),
            func.coalesce(images.c.image_count, 0),
            func.coalesce(images.c.has_cover, False),
            images.c.cover_image_id,
        )
        .outerjoin(lines, lines.c.document_id == Document.id)
        .outerjoin(images, images.c.document_id == Document.id)
        .where(Document.user_id == user.id)
        .order_by(Document.updated_at.desc(), Document.id.desc())
    )
    return [
        DocumentListItem(
            **DocumentOut.model_validate(doc).model_dump(),
            line_count=lc,
            translated_count=tc,
            image_count=ic,
            has_cover=hc,
            cover_image_id=cid,
            progress=progress(lc, tc, ic),
        )
        for doc, lc, tc, ic, hc, cid in rows
    ]


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Document:
    return scoped(db, Document, document_id, user.id)


@router.post("", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def create_document(
    body: DocumentCreate, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Document:
    """The desktop "New document" dialog: pasted source text is split into sentence
    lines by the ported build_new_file."""
    check_placement(db, user.id, body.series_id, body.volume_id)
    parsed = None
    if body.raw_text.strip():
        parsed = parse_file_content(build_new_file(body.raw_text))
        check_line_count(parsed[0])
    doc = Document(
        user_id=user.id,
        series_order=next_series_order(db, body.series_id),
        **body.model_dump(exclude={"raw_text"}),
    )
    db.add(doc)
    db.flush()
    if parsed:
        raw, translated, _ = parsed
        write_lines(db, doc.id, lines_to_db_rows(raw, translated))
    arrange(db, db.get(Series, doc.series_id))
    db.flush()
    return doc


@router.patch("/{document_id}", response_model=DocumentOut)
def update_document(
    document_id: int,
    body: DocumentUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Document:
    doc = scoped(db, Document, document_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    old_series_id = doc.series_id
    series_id = changes.get("series_id", doc.series_id)
    moving = series_id != doc.series_id
    if moving:
        # A chapter changing series leaves its old volume unless the body names a new one.
        changes.setdefault("volume_id", None)
    check_placement(db, user.id, series_id, changes.get("volume_id", doc.volume_id))
    if moving:
        changes["series_order"] = next_series_order(db, series_id)
    volume_changed = "volume_id" in changes and changes["volume_id"] != doc.volume_id
    for field, value in changes.items():
        setattr(doc, field, value)
    db.flush()
    if moving:
        arrange(db, db.get(Series, old_series_id))
        arrange(db, db.get(Series, series_id))
    elif volume_changed:
        send_to_volume_end(db, db.get(Series, series_id), [doc], doc.volume_id)
    db.flush()
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    db.delete(scoped(db, Document, document_id, user.id))
    db.flush()


@router.post("/merge", response_model=DocumentOut)
def merge(
    body: MergeRequest, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Document:
    try:
        return merge_documents(db, user.id, body.document_ids, body.title)
    except NotOwned:
        # The ids are in the body, so missing and foreign look the same (422).
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "document_ids: no such item"
        ) from None
    except RestructureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.post("/{document_id}/split", response_model=list[DocumentOut])
def split(
    document_id: int,
    body: SplitRequest,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[Document]:
    cuts = [(cut.start, cut.title) for cut in body.cuts]
    try:
        return split_document(db, user.id, document_id, cuts)
    except NotOwned:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found") from None
    except RestructureError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
