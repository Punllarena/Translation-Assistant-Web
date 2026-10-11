from fastapi import Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from api.deps import current_user, db_session, scoped
from api.models import Document, DocumentImage, User
from api.routing import api_router
from api.schemas.images import ImageOut, ImageUpdate
from api.uploads import sniff_image

router = api_router(tags=["images"])

MEDIA_TYPES = {"png": "image/png", "jpg": "image/jpeg", "gif": "image/gif", "webp": "image/webp"}


def scoped_image(db: Session, image_id: int, user_id: int) -> DocumentImage:
    """An image is owned through its document; 404 for missing and foreign alike."""
    image = db.scalar(
        select(DocumentImage)
        .options(defer(DocumentImage.data))
        .join(Document)
        .where(DocumentImage.id == image_id, Document.user_id == user_id)
    )
    if image is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return image


@router.get("/documents/{document_id}/images", response_model=list[ImageOut])
def list_images(
    document_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> list[DocumentImage]:
    doc = scoped(db, Document, document_id, user.id)
    return list(
        db.scalars(
            select(DocumentImage)
            .options(defer(DocumentImage.data))
            .where(DocumentImage.document_id == doc.id)
            .order_by(DocumentImage.anchor_position, DocumentImage.id)
        )
    )


@router.get("/images/{image_id}", response_class=Response)
def get_image(
    image_id: int, user: User = Depends(current_user), db: Session = Depends(db_session)
) -> Response:
    """The image bytes. The type comes from the bytes, and anything that is not a known
    raster format is served as an opaque download, so an imported SVG can never run
    script in the app's origin. An image row's bytes never change (a new cover is a new
    row), so the browser may cache it for good."""
    image = scoped_image(db, image_id, user.id)
    return Response(
        content=image.data,
        media_type=MEDIA_TYPES.get(sniff_image(image.data), "application/octet-stream"),
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
            "Vary": "Cookie",  # the URL is user-agnostic; keep one user's image from another's cache
        },
    )


@router.patch("/images/{image_id}", response_model=ImageOut)
def update_image(
    image_id: int,
    body: ImageUpdate,
    user: User = Depends(current_user),
    db: Session = Depends(db_session),
) -> DocumentImage:
    image = scoped_image(db, image_id, user.id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(image, field, value)
    db.flush()
    return image
