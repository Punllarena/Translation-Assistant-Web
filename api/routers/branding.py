"""Branding: a public read for the pre-login pages, admin-only writes, cached image bytes.

The image route is public because an ``<img>`` and a favicon ``<link>`` cannot send credentials
selectively on the login page. Every image is served with a sandboxing CSP and ``nosniff``, and
the SPA only ever shows it through ``<img>`` / ``<link>``, so an uploaded SVG cannot run script in
the app's origin.
"""

from fastapi import Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from api import branding
from api.deps import db_session, require_admin
from api.models import BrandImage, User
from api.routing import api_router
from api.schemas.branding import BrandingIn, BrandingOut
from api.uploads import read_capped

router = api_router(tags=["branding"])

ALLOWED = {
    "logo": "logo must be a PNG, WebP or SVG image",
    "logo_dark": "dark-mode logo must be a PNG, WebP or SVG image",
    "favicon": "favicon must be a PNG, WebP, SVG or ICO image",
}
IMAGE_HEADERS = {
    "Cache-Control": "public, max-age=31536000, immutable",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "sandbox",
}


def _unknown_kind(kind: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"no brand image named {kind!r}")


@router.get("/branding", response_model=BrandingOut)
def read_branding(db: Session = Depends(db_session)) -> dict:
    """The name, the show-name flag and the image ids; no login (pre-login pages need it)."""
    return branding.public(db)


@router.get("/branding/image/{image_id}", response_class=Response)
def read_image(image_id: int, db: Session = Depends(db_session)) -> Response:
    """The bytes, typed from the bytes and cached for good (a replace is a new id)."""
    data = db.scalar(select(BrandImage.data).where(BrandImage.id == image_id))
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return Response(
        content=data, media_type=branding.media_type(data), headers=IMAGE_HEADERS
    )


@router.put("/admin/branding", response_model=BrandingOut)
def put_branding(
    body: BrandingIn, _: User = Depends(require_admin), db: Session = Depends(db_session)
) -> dict:
    """Save the name and the show-name flag; a blank name means the default."""
    try:
        name = branding.clean_name(body.name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    branding.set_text(db, name, body.show_name)
    return branding.public(db)


@router.put("/admin/branding/{kind}", response_model=BrandingOut)
def upload_image(
    kind: str,
    file: UploadFile = File(...),
    _: User = Depends(require_admin),
    db: Session = Depends(db_session),
) -> dict:
    if kind not in branding.KINDS:
        raise _unknown_kind(kind)
    data = read_capped(file, branding.MAX_IMAGE_BYTES)
    if branding.sniff_brand_image(data, kind) is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, ALLOWED[kind])
    branding.set_image(db, kind, data)
    return branding.public(db)


@router.delete("/admin/branding/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image(
    kind: str, _: User = Depends(require_admin), db: Session = Depends(db_session)
) -> None:
    """Remove the kind's image; already absent is still 204."""
    if kind not in branding.KINDS:
        raise _unknown_kind(kind)
    branding.clear_image(db, kind)


@router.delete("/admin/branding", status_code=status.HTTP_204_NO_CONTENT)
def reset_branding(_: User = Depends(require_admin), db: Session = Depends(db_session)) -> None:
    """Back to the defaults: the default name, the flag on and no images."""
    branding.reset(db)
