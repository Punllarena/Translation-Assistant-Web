from types import SimpleNamespace

import pytest
from sqlalchemy import inspect as sa_inspect

from api import covers
from api.image_moves import IS_ILLUSTRATIONS, NO_VOLUME
from api.models import Document, DocumentImage, Volume, VolumeCover

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _vol(db, series, order, name):
    volume = Volume(series_id=series.id, subtitle=name, volume_order=order)
    db.add(volume)
    db.flush()
    return volume


def _pic(db, doc, name, anchor=0, data=PNG):
    image = DocumentImage(
        document_id=doc.id, anchor_position=anchor, src_path=name, data=data
    )
    db.add(image)
    db.flush()
    return image


def _illustrations(db, user, series, volume, order=9):
    doc = Document(
        user_id=user.id,
        series_id=series.id,
        volume_id=volume.id,
        title="Illustrations",
        chapter_title="Illustrations",
        series_order=order,
        is_illustrations=True,
    )
    db.add(doc)
    db.flush()
    return doc


def _names(db, doc_id):
    rows = db.query(DocumentImage).filter_by(document_id=doc_id)
    return [im.src_path for im in rows.order_by(DocumentImage.anchor_position, DocumentImage.id)]


@pytest.fixture
def gallery(db, me, make_series, make_doc):
    """V1 (a cover), chapters c1 [b anchor 0, a anchor 2], c2 [c]; loose chapter [d]."""
    series = make_series(me, "Gallery")
    v1 = _vol(db, series, 1, "V1")
    c1 = make_doc(me, ["one"], series=series, volume=v1, order=1, title="One")
    c2 = make_doc(me, ["two"], series=series, volume=v1, order=2, title="Two")
    loose = make_doc(me, ["loose"], series=series, order=3, title="Loose")
    a = _pic(db, c1, "a.png", anchor=2)
    b = _pic(db, c1, "b.png", anchor=0)
    c = _pic(db, c2, "c.png")
    d = _pic(db, loose, "d.png")
    cover = covers.set_cover(db, v1.id, PNG, "cover.png")
    db.flush()
    return SimpleNamespace(
        series=series, v1=v1, c1=c1, c2=c2, loose=loose,
        a=a, b=b, c=c, d=d, cover=cover,
    )


def test_listing_orders_covers_then_chapters_then_anchors(app_client, db, gallery):
    db.expire_all()
    r = app_client.get(f"/series/{gallery.series.id}/images")
    assert r.status_code == 200, r.text
    body = r.json()
    assert [(row["kind"], row["src_path"]) for row in body] == [
        ("cover", "cover.png"),
        ("image", "b.png"),
        ("image", "a.png"),
        ("image", "c.png"),
        ("image", "d.png"),
    ]
    cover_row = body[0]
    assert cover_row["id"] == gallery.cover.id
    assert (cover_row["volume_id"], cover_row["document_id"]) == (gallery.v1.id, None)
    assert body[1]["id"] == gallery.b.id
    assert body[1]["document_id"] == gallery.c1.id
    assert body[-1]["volume_id"] is None


def test_listing_never_loads_bytes(app_client, db, gallery):
    db.expire_all()
    body = app_client.get(f"/series/{gallery.series.id}/images").json()
    assert "data" not in body[0]
    assert all(
        "data" in sa_inspect(image).unloaded
        for image in db.identity_map.values()
        if isinstance(image, DocumentImage)
    )


def test_listing_other_users_series_is_404(app_client, other_users_series_id):
    assert app_client.get(f"/series/{other_users_series_id}/images").status_code == 404


def test_set_cover_copies_bytes(app_client, db, gallery):
    old_id = gallery.cover.id
    r = app_client.post(f"/images/{gallery.a.id}/cover")
    assert r.status_code == 200, r.text
    assert r.json()["src_path"] == "cover.png"
    db.expire_all()
    rows = db.query(VolumeCover).filter_by(volume_id=gallery.v1.id).all()
    assert [row.src_path for row in rows] == ["cover.png"]
    assert rows[0].data == PNG
    assert rows[0].id != old_id
    assert db.get(VolumeCover, old_id) is None


def test_set_cover_refuses_svg(app_client, db, gallery):
    svg = _pic(db, gallery.c2, "vector.svg", data=SVG)
    r = app_client.post(f"/images/{svg.id}/cover")
    assert (r.status_code, r.json()["detail"]) == (415, covers.NOT_IMAGE)
    db.expire_all()
    assert db.query(VolumeCover).filter_by(volume_id=gallery.v1.id).one().src_path == "cover.png"


def test_set_cover_refuses_loose_chapter(app_client, db, gallery):
    r = app_client.post(f"/images/{gallery.d.id}/cover")
    assert (r.status_code, r.json()["detail"]) == (
        409, "a chapter outside a volume has no volume cover"
    )


def test_move_renames_on_clash(app_client, db, me, gallery):
    illus = _illustrations(db, me, gallery.series, gallery.v1)
    _pic(db, illus, "b.png")
    r = app_client.post(f"/images/{gallery.b.id}/move")
    assert r.status_code == 204, r.text
    db.expire_all()
    assert _names(db, illus.id) == ["b.png", "b-2.png"]
    assert db.get(DocumentImage, gallery.b.id).document_id == illus.id


def test_move_refused_for_loose_and_syosetu(
    app_client, db, me, make_series, make_doc, gallery
):
    r = app_client.post(f"/images/{gallery.d.id}/move")
    assert (r.status_code, r.json()["detail"]) == (409, NO_VOLUME)
    syo = make_series(me, "Syo")
    syo.syosetu_url = "https://ncode.syosetu.com/n1/"
    sv = _vol(db, syo, 1, "SV")
    sd = make_doc(me, ["text"], series=syo, volume=sv, order=1, title="sd")
    pic = _pic(db, sd, "sd.png")
    r = app_client.post(f"/images/{pic.id}/move")
    assert (r.status_code, r.json()["detail"]) == (
        409, "a syosetu series has no Illustrations chapter"
    )


def test_move_last_image_of_illustrations_impossible(app_client, db, me, gallery):
    illus = _illustrations(db, me, gallery.series, gallery.v1)
    pic = _pic(db, illus, "plate.png")
    r = app_client.post(f"/images/{pic.id}/move")
    assert (r.status_code, r.json()["detail"]) == (409, IS_ILLUSTRATIONS)
    assert db.get(DocumentImage, pic.id) is not None


def test_delete_image(app_client, db, gallery):
    r = app_client.delete(f"/images/{gallery.a.id}")
    assert r.status_code == 204
    db.expire_all()
    assert db.get(DocumentImage, gallery.a.id) is None
    assert _names(db, gallery.c1.id) == ["b.png"]


def test_delete_last_illustrations_image_deletes_chapter(app_client, db, me, gallery):
    # the volume's only chapter: deleting it must leave the volume and arrange() must cope
    v2 = _vol(db, gallery.series, 2, "V2")
    illus = _illustrations(db, me, gallery.series, v2)
    pic = _pic(db, illus, "plate.png")
    r = app_client.delete(f"/images/{pic.id}")
    assert r.status_code == 204
    db.expire_all()
    assert db.get(Document, illus.id) is None
    assert db.get(Volume, v2.id) is not None
    orders = [
        doc.series_order
        for doc in db.query(Document)
        .filter_by(series_id=gallery.series.id)
        .order_by(Document.series_order)
    ]
    assert orders == list(range(1, len(orders) + 1))


def test_delete_keeps_a_non_illustrations_chapter(app_client, db, gallery):
    r = app_client.delete(f"/images/{gallery.c.id}")
    assert r.status_code == 204
    db.expire_all()
    assert db.get(Document, gallery.c2.id) is not None


@pytest.mark.parametrize(
    ("method", "suffix"),
    [("post", "/cover"), ("post", "/move"), ("delete", "")],
)
def test_image_actions_on_other_users_image_are_404(
    app_client, db, me, make_user, make_doc, method, suffix
):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    image = _pic(db, theirs, "theirs.png")
    r = getattr(app_client, method)(f"/images/{image.id}{suffix}")
    assert r.status_code == 404
