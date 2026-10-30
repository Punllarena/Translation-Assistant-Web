"""The Gallery: every image of a series (volume covers included) in display order, and the
three things a viewer may do with one — make it its volume's cover, move it to the
Illustrations chapter, or delete it. Never a thumbnail: tiles load the full bytes from
``GET /images/{id}`` and ``GET /covers/{id}``."""

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import covers
from api.deps import current_user, db_session, scoped
from api.illustrations import IllustrationsRule, rule_conflict
from api.image_moves import check_can_move, drop_if_empty, move_images
from api.library import arrange
from api.models import Document, DocumentImage, Series, User, Volume, VolumeCover
from api.routers.images import scoped_image
from api.routing import api_router
from api.schemas.gallery import GalleryImageOut
from api.schemas.volumes import VolumeCoverOut
from api.uploads import sniff_image

router = api_router(tags=["gallery"])

NO_VOLUME_COVER = "a chapter outside a volume has no volume cover"


@router.get("/series/{series_id}/images", response_model=list[GalleryImageOut])
def list_series_images(
    series_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[GalleryImageOut]:
    """Volumes by ``volume_order`` (loose chapters last), each volume's cover first, then its
    chapters by ``series_order``, then each chapter's images by anchor. No bytes."""
    series = scoped(db, Series, series_id, user.id)
    volumes = list(
        db.scalars(
            select(Volume)
            .where(Volume.series_id == series.id)
            .order_by(Volume.volume_order, Volume.id)
        )
    )
    rank = {volume.id: i for i, volume in enumerate(volumes)}
    cover_rows = {
        row.volume_id: row
        for row in db.execute(
            select(VolumeCover.id, VolumeCover.volume_id, VolumeCover.src_path).where(
                VolumeCover.volume_id.in_(list(rank))
            )
        )
    }
    images = list(
        db.execute(
            select(
                DocumentImage.id.label("image_id"),
                DocumentImage.anchor_position,
                DocumentImage.src_path,
                DocumentImage.exclude_export,
                Document.volume_id,
                Document.id.label("document_id"),
                Document.series_order,
            )
            .join(Document, Document.id == DocumentImage.document_id)
            .where(Document.series_id == series.id)
        )
    )
    loose = len(rank)
    images.sort(
        key=lambda row: (
            rank.get(row.volume_id, loose),
            row.series_order,
            row.document_id,
            row.anchor_position,
            row.image_id,
        )
    )
    by_volume: dict[int | None, list] = {}
    for row in images:
        by_volume.setdefault(row.volume_id, []).append(row)
    out: list[GalleryImageOut] = []
    for volume in volumes:
        cover = cover_rows.get(volume.id)
        if cover is not None:
            out.append(
                GalleryImageOut(
                    id=cover.id,
                    kind="cover",
                    volume_id=volume.id,
                    document_id=None,
                    src_path=cover.src_path,
                    anchor_position=0,
                    exclude_export=False,
                )
            )
        out.extend(
            GalleryImageOut(
                id=row.image_id,
                kind="image",
                volume_id=volume.id,
                document_id=row.document_id,
                src_path=row.src_path,
                anchor_position=row.anchor_position,
                exclude_export=row.exclude_export,
            )
            for row in by_volume.get(volume.id, ())
        )
    out.extend(
        GalleryImageOut(
            id=row.image_id,
            kind="image",
            volume_id=None,
            document_id=row.document_id,
            src_path=row.src_path,
            anchor_position=row.anchor_position,
            exclude_export=row.exclude_export,
        )
        for row in by_volume.get(None, ())
    )
    return out


@router.post("/images/{image_id}/cover", response_model=VolumeCoverOut)
def set_image_as_cover(
    image_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> VolumeCover:
    """Copy the image's bytes into its chapter's volume cover (a new row, as the upload does)."""
    image = scoped_image(db, image_id, user.id)
    doc = image.document
    if doc.volume_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_VOLUME_COVER)
    ext = sniff_image(image.data)
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, covers.NOT_IMAGE)
    return covers.set_cover(db, doc.volume_id, image.data, f"cover.{ext}")


@router.post("/images/{image_id}/move", status_code=status.HTTP_204_NO_CONTENT)
def move_image_to_illustrations(
    image_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    """Append the image to the end of its volume's Illustrations chapter (409 when it may not)."""
    image = scoped_image(db, image_id, user.id)
    doc = image.document
    try:
        volume = check_can_move(db, doc)
    except IllustrationsRule as exc:
        raise rule_conflict(exc) from None
    move_images(db, user, volume, [image], order=doc.series_order)
    db.flush()
    arrange(db, db.get(Series, doc.series_id))
    db.flush()


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    image_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    """Remove the image; an Illustrations chapter it leaves empty goes with it."""
    image = scoped_image(db, image_id, user.id)
    doc = image.document
    db.delete(image)
    db.flush()
    drop_if_empty(db, doc)
    db.flush()
