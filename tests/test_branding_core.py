"""Branding rules: image type decided by bytes, the name's limits, and the one-row store."""

import pytest
from sqlalchemy import func, select

from api import branding
from api.models import BrandImage

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
SVG_PROLOG = (
    b'\xef\xbb\xbf<?xml version="1.0" encoding="UTF-8"?>'
    b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">'
    b"<svg></svg>"
)
ICO = b"\x00\x00\x01\x00" + b"\x00" * 16
JPEG = b"\xff\xd8\xff" + b"\x00" * 16
GIF = b"GIF89a" + b"\x00" * 16


def test_sniff_accepts_each_type():
    assert branding.sniff_brand_image(PNG, "logo") == "png"
    assert branding.sniff_brand_image(WEBP, "logo") == "webp"
    assert branding.sniff_brand_image(SVG, "logo") == "svg"
    assert branding.sniff_brand_image(SVG_PROLOG, "logo") == "svg"
    assert branding.sniff_brand_image(ICO, "favicon") == "ico"


def test_sniff_refuses_html_named_svg():
    assert branding.sniff_brand_image(b"<html><svg></svg></html>", "logo") is None
    assert branding.sniff_brand_image(
        b"<!DOCTYPE html><html><body><svg></svg></body></html>", "favicon"
    ) is None


def test_ico_only_for_favicon():
    assert branding.sniff_brand_image(ICO, "logo") is None
    assert branding.sniff_brand_image(ICO, "logo_dark") is None


def test_jpeg_and_gif_refused():
    assert branding.sniff_brand_image(JPEG, "logo") is None
    assert branding.sniff_brand_image(GIF, "favicon") is None


def test_clean_name():
    assert branding.clean_name("  A  ") == "A"
    assert branding.clean_name("   ") is None
    assert branding.clean_name("x" * 60) == "x" * 60
    with pytest.raises(ValueError):
        branding.clean_name("x" * 61)


def test_public_defaults(db):
    assert branding.public(db) == {
        "name": "Translation Assistant",
        "show_name": True,
        "logo_id": None,
        "logo_dark_id": None,
        "favicon_id": None,
    }


def test_set_image_replaces_and_changes_id(db):
    first = branding.set_image(db, "logo", PNG)
    second = branding.set_image(db, "logo", PNG + b"x")
    assert second.id != first.id
    assert db.scalar(
        select(func.count()).select_from(BrandImage).where(BrandImage.kind == "logo")
    ) == 1


def test_reset_clears_everything(db):
    branding.set_text(db, "My Site", False)
    branding.set_image(db, "logo", PNG)
    branding.set_image(db, "favicon", ICO)

    branding.reset(db)

    assert branding.public(db) == {
        "name": "Translation Assistant",
        "show_name": True,
        "logo_id": None,
        "logo_dark_id": None,
        "favicon_id": None,
    }
    assert db.scalar(select(func.count()).select_from(BrandImage)) == 0
