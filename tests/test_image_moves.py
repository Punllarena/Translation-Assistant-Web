import pytest

from api.image_moves import IS_ILLUSTRATIONS, NO_VOLUME, free_name
from api.models import Document, DocumentImage, Volume


def _vol(db, series, order, name):
    v = Volume(series_id=series.id, subtitle=name, volume_order=order)
    db.add(v)
    db.flush()
    return v


def _pics(db, doc, *names):
    for name in names:
        db.add(DocumentImage(document_id=doc.id, anchor_position=0,
                             src_path=name, data=name.encode()))
    db.flush()


def _held(db, doc_id):
    rows = db.query(DocumentImage).filter_by(document_id=doc_id)
    return [im.src_path for im in rows.order_by(DocumentImage.anchor_position, DocumentImage.id)]


def _mark(client, doc, value=True):
    r = client.patch(f"/documents/{doc.id}", json={"is_illustrations": value})
    assert r.status_code == 200, r.text


@pytest.fixture
def lib(app_client, db, me, make_series, make_doc):
    """V1 = [a (Illustrations, x.png), t (text, y.png and x.png)]; V2 = [d (text, z.png)]."""
    s = make_series(me, "Lib")
    v1, v2 = _vol(db, s, 1, "V1"), _vol(db, s, 2, "V2")
    a = make_doc(me, [], series=s, volume=v1, order=1, title="a")
    t = make_doc(me, ["some text"], series=s, volume=v1, order=2, title="t")
    d = make_doc(me, ["more text"], series=s, volume=v2, order=3, title="d")
    _mark(app_client, a)
    _pics(db, a, "x.png")
    _pics(db, t, "y.png", "x.png")
    _pics(db, d, "z.png")
    db.flush()
    return s, v1, v2, {"a": a, "t": t, "d": d}


def test_free_name():
    assert free_name(set(), "a.jpg") == "a.jpg"
    assert free_name({"a.jpg"}, "a.jpg") == "a-2.jpg"
    assert free_name({"a.jpg", "a-2.jpg"}, "a.jpg") == "a-3.jpg"
    assert free_name({"noext"}, "noext") == "noext-2"


def test_delete_move_appends_to_existing_illustrations(app_client, db, lib):
    s, v1, v2, d = lib
    r = app_client.delete(f"/documents/{d['t'].id}?images=move")
    assert r.status_code == 204
    db.expire_all()
    assert db.get(Document, d["t"].id) is None
    assert _held(db, d["a"].id) == ["x.png", "y.png", "x-2.png"]


def test_delete_move_creates_illustrations_chapter(app_client, db, lib):
    s, v1, v2, d = lib
    r = app_client.delete(f"/documents/{d['d'].id}?images=move")
    assert r.status_code == 204
    db.expire_all()
    created = db.query(Document).filter_by(volume_id=v2.id, is_illustrations=True).one()
    assert (created.title, created.chapter_title) == ("Illustrations", "Illustrations")
    first = (db.query(Document).filter_by(volume_id=v2.id)
             .order_by(Document.series_order).first())
    assert first.id == created.id  # arrange() put it first in its volume
    assert _held(db, created.id) == ["z.png"]


def test_delete_move_refused_outside_volume(app_client, db, me, make_doc, lib):
    s, v1, v2, d = lib
    loose = make_doc(me, ["loose"], series=s, order=9, title="loose")
    _pics(db, loose, "loose.png")
    r = app_client.delete(f"/documents/{loose.id}?images=move")
    assert (r.status_code, r.json()["detail"]) == (409, NO_VOLUME)
    assert app_client.get(f"/documents/{loose.id}").status_code == 200


def test_delete_move_refused_in_syosetu_series(app_client, db, me, make_series, make_doc):
    syo = make_series(me, "Syo")
    syo.syosetu_url = "https://ncode.syosetu.com/n1/"
    sv = _vol(db, syo, 1, "SV")
    sd = make_doc(me, ["text"], series=syo, volume=sv, order=1, title="sd")
    _pics(db, sd, "sd.png")
    r = app_client.delete(f"/documents/{sd.id}?images=move")
    assert (r.status_code, r.json()["detail"]) == (
        409, "a syosetu series has no Illustrations chapter")
    assert app_client.get(f"/documents/{sd.id}").status_code == 200


def test_delete_move_refused_for_illustrations_chapter(app_client, db, lib):
    s, v1, v2, d = lib
    r = app_client.delete(f"/documents/{d['a'].id}?images=move")
    assert (r.status_code, r.json()["detail"]) == (409, IS_ILLUSTRATIONS)
    assert app_client.get(f"/documents/{d['a'].id}").status_code == 200


def test_delete_default_still_drops_images(app_client, db, lib):
    s, v1, v2, d = lib
    t_id = d["t"].id
    assert app_client.delete(f"/documents/{t_id}").status_code == 204
    db.expire_all()
    assert db.query(DocumentImage).filter_by(document_id=t_id).count() == 0


def test_delete_move_without_images_creates_nothing(app_client, db, me, make_doc, lib):
    s, v1, v2, d = lib
    plain = make_doc(me, ["plain"], series=s, volume=v2, order=4, title="plain")
    assert app_client.delete(f"/documents/{plain.id}?images=move").status_code == 204
    db.expire_all()
    assert db.query(Document).filter_by(volume_id=v2.id, is_illustrations=True).count() == 0
