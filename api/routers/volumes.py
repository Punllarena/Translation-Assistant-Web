from fastapi import Depends, File, HTTPException, UploadFile, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.deps import current_user, db_session, scoped, scoped_volume
from api.errors import conflict
from api.library import arrange, send_to_volume_end
from api.models import Document, DocumentImage, Series, User, Volume, VolumeSyosetuGroup
from api.routing import api_router
from api.schemas.documents import DocumentIds, DocumentOut
from api.schemas.volumes import CoverOut, VolumeCreate, VolumeMerge, VolumeOut, VolumeUpdate
from api.uploads import read_capped, sniff_image

router = api_router(tags=["volumes"])

TITLE_TAKEN = "a volume with that title exists in this series"
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@router.get("/volumes", response_model=list[VolumeOut])
def list_all_volumes(
    user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Volume]:
    return list(
        db.scalars(
            select(Volume)
            .join(Series, Series.id == Volume.series_id)
            .where(Series.user_id == user.id)
            .order_by(Volume.series_id, Volume.volume_order, Volume.id)
        )
    )


@router.get("/series/{series_id}/volumes", response_model=list[VolumeOut])
def list_volumes(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[Volume]:
    series = scoped(db, Series, series_id, user.id)
    return list(
        db.scalars(
            select(Volume)
            .where(Volume.series_id == series.id)
            .order_by(Volume.volume_order, Volume.id)
        )
    )


@router.post(
    "/series/{series_id}/volumes", response_model=VolumeOut, status_code=status.HTTP_201_CREATED
)
def create_volume(
    series_id: int,
    body: VolumeCreate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Volume:
    series = scoped(db, Series, series_id, user.id)
    order = body.volume_order
    if order is None:
        order = db.scalar(
            select(func.coalesce(func.max(Volume.volume_order), 0) + 1).where(
                Volume.series_id == series.id
            )
        )
    volume = Volume(
        series_id=series.id, volume_order=order, **body.model_dump(exclude={"volume_order"})
    )
    try:
        with db.begin_nested():
            db.add(volume)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    return volume


@router.patch("/volumes/{volume_id}", response_model=VolumeOut)
def update_volume(
    volume_id: int,
    body: VolumeUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> Volume:
    volume = scoped_volume(db, volume_id, user.id)
    changes = body.model_dump(exclude_unset=True)
    try:
        with db.begin_nested():
            for field, value in changes.items():
                setattr(volume, field, value)
    except IntegrityError as exc:
        raise conflict(exc, TITLE_TAKEN) from exc
    if "volume_order" in changes:
        db.flush()
        arrange(db, volume.series)
        db.flush()
    return volume


@router.delete("/volumes/{volume_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_volume(
    volume_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    """Chapters survive, unassigned: documents.volume_id is ON DELETE SET NULL."""
    volume = scoped_volume(db, volume_id, user.id)
    series = volume.series
    db.delete(volume)
    db.flush()
    db.expire_all()
    arrange(db, series)
    db.flush()


@router.post("/series/{series_id}/volumes/merge", response_model=VolumeOut)
def merge_volumes(
    series_id: int, body: VolumeMerge,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> Volume:
    """Merge several volumes into ``into``: it keeps its own title and EPUB details and
    takes the others' chapters and syosetu headings; the others are deleted."""
    series = scoped(db, Series, series_id, user.id)
    ids = set(body.volume_ids)
    if len(ids) < 2:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "volume_ids: pick at least two volumes")
    if body.into not in ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "into must be one of volume_ids")
    found = set(db.scalars(
        select(Volume.id).where(Volume.id.in_(ids), Volume.series_id == series.id)))
    if found != ids:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "volume_ids: every volume must be in this series")
    others = ids - {body.into}
    db.execute(update(Document).where(Document.volume_id.in_(others))
               .values(volume_id=body.into))
    db.execute(update(VolumeSyosetuGroup).where(VolumeSyosetuGroup.volume_id.in_(others))
               .values(volume_id=body.into))
    db.execute(delete(Volume).where(Volume.id.in_(others)))
    db.flush()
    db.expire_all()
    arrange(db, series)
    db.flush()
    return db.get(Volume, body.into)


@router.post("/volumes/{volume_id}/documents", response_model=list[DocumentOut])
def assign_documents(
    volume_id: int,
    body: DocumentIds,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> list[Document]:
    """Put chapters of the volume's series into it. All or nothing."""
    volume = scoped_volume(db, volume_id, user.id)
    wanted = set(body.document_ids)
    docs = list(
        db.scalars(
            select(Document)
            .where(
                Document.id.in_(wanted),
                Document.user_id == user.id,
                Document.series_id == volume.series_id,
            )
            .order_by(Document.series_order, Document.id)
        )
    )
    if len(docs) != len(wanted):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "document_ids: every chapter must be yours and in this volume's series",
        )
    send_to_volume_end(db, volume.series, docs, volume.id)
    db.flush()
    return docs


@router.put("/documents/{document_id}/cover", response_model=CoverOut)
def set_cover(
    document_id: int,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> DocumentImage:
    """Designate a chapter's cover (the desktop replace_document_cover): any previous
    cover on the chapter is replaced."""
    doc = scoped(db, Document, document_id, user.id)
    data = read_capped(file, MAX_IMAGE_BYTES)
    ext = sniff_image(data)
    if ext is None:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "cover must be a PNG, JPEG, GIF or WebP image"
        )
    db.execute(
        delete(DocumentImage).where(DocumentImage.document_id == doc.id, DocumentImage.is_cover)
    )
    cover = DocumentImage(
        document_id=doc.id, anchor_position=0, is_cover=True, src_path=f"cover.{ext}", data=data
    )
    db.add(cover)
    db.flush()
    return cover


@router.delete("/documents/{document_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
def clear_cover(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    doc = scoped(db, Document, document_id, user.id)
    db.execute(
        delete(DocumentImage).where(DocumentImage.document_id == doc.id, DocumentImage.is_cover)
    )
