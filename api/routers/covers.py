from fastapi import Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from api import covers
from api.deps import current_user, db_session, scoped, scoped_volume
from api.models import Series, User, Volume, VolumeCover
from api.routers.images import MEDIA_TYPES
from api.routing import api_router
from api.schemas.volumes import CoverUrl, SeriesCoverVolume, VolumeCoverOut
from api.uploads import read_capped, sniff_image

router = api_router(tags=["covers"])

http_client = covers.client  # the seam tests replace


@router.put("/volumes/{volume_id}/cover", response_model=VolumeCoverOut)
def upload_cover(
    volume_id: int,
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> VolumeCover:
    """Set the volume's cover from a file; any previous cover is replaced."""
    volume = scoped_volume(db, volume_id, user.id)
    data = read_capped(file, covers.MAX_IMAGE_BYTES)
    ext = sniff_image(data)
    if ext is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, covers.NOT_IMAGE)
    return covers.set_cover(db, volume.id, data, f"cover.{ext}")


@router.post("/volumes/{volume_id}/cover/url", response_model=VolumeCoverOut)
def fetch_cover(
    volume_id: int, body: CoverUrl,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> VolumeCover:
    """Download the image at a direct image address and keep it as the volume's cover."""
    volume = scoped_volume(db, volume_id, user.id)
    try:
        with http_client() as c:
            data, ext = covers.fetch_image(c, body.url)
    except covers.CoverFetchError as exc:
        raise HTTPException(exc.status_code, exc.message) from None
    return covers.set_cover(db, volume.id, data, f"cover.{ext}")


@router.delete("/volumes/{volume_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
def clear_cover(
    volume_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> None:
    volume = scoped_volume(db, volume_id, user.id)
    covers.clear_cover(db, volume.id)


@router.get("/covers/{cover_id}", response_class=Response)
def get_cover(
    cover_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Response:
    """The cover's bytes, served like /images/{id}: type from the bytes, cached for good
    (a replaced cover is a new id)."""
    data = db.scalar(
        select(VolumeCover.data).join(Volume, Volume.id == VolumeCover.volume_id)
        .join(Series, Series.id == Volume.series_id)
        .where(VolumeCover.id == cover_id, Series.user_id == user.id)
    )
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return Response(
        content=data,
        media_type=MEDIA_TYPES.get(sniff_image(data), "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Vary": "Cookie",
        },
    )


@router.put("/series/{series_id}/cover-volume", status_code=status.HTTP_204_NO_CONTENT)
def choose_series_cover(
    series_id: int, body: SeriesCoverVolume,
    user: User = Depends(current_user), db: Session = Depends(db_session),
) -> None:
    """Make ``volume_id``'s cover the series cover; null clears the choice."""
    series = scoped(db, Series, series_id, user.id)
    if body.volume_id is not None and db.scalar(select(Volume.id).where(
            Volume.id == body.volume_id, Volume.series_id == series.id)) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT,
                            "volume_id: the volume must be in this series")
    # clear first: at most one flagged volume per series (uq_volumes_series_cover)
    db.execute(update(Volume).where(Volume.series_id == series.id, Volume.is_series_cover)
               .values(is_series_cover=False))
    if body.volume_id is not None:
        db.execute(update(Volume).where(Volume.id == body.volume_id)
                   .values(is_series_cover=True))
    db.flush()
    db.expire_all()
