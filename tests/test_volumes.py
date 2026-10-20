import pytest
from sqlalchemy import select

from api.models import Document, DocumentImage, Volume

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def series(me, make_series):
    return make_series(me)


def _volume(client, series, title="V1"):
    return client.post(f"/series/{series.id}/volumes", json={"title": title})


def test_create_appends_volume_order_and_lists_in_order(app_client, series):
    a, b = _volume(app_client, series, "V1"), _volume(app_client, series, "V2")
    assert (a.status_code, a.json()["volume_order"], b.json()["volume_order"]) == (201, 1, 2)
    listed = app_client.get(f"/series/{series.id}/volumes").json()
    assert [v["title"] for v in listed] == ["V1", "V2"]


def test_duplicate_title_in_series_is_409(app_client, series):
    _volume(app_client, series)
    assert _volume(app_client, series).status_code == 409


def test_same_title_in_another_series_is_fine(app_client, me, make_series, series):
    _volume(app_client, series)
    assert _volume(app_client, make_series(me, "Other")).status_code == 201


def test_patch_sets_epub_metadata(app_client, series):
    vid = _volume(app_client, series).json()["id"]
    r = app_client.patch(f"/volumes/{vid}", json={"epub_author": "Author", "epub_language": "ja"})
    assert (r.json()["epub_author"], r.json()["epub_language"]) == ("Author", "ja")


def test_rename_onto_existing_is_409(app_client, series):
    _volume(app_client, series, "V1")
    vid = _volume(app_client, series, "V2").json()["id"]
    assert app_client.patch(f"/volumes/{vid}", json={"title": "V1"}).status_code == 409


def test_delete_volume_unassigns_chapters(app_client, db, me, series, make_doc):
    vol = Volume(series_id=series.id, title="V")
    db.add(vol)
    db.flush()
    doc = make_doc(me, series=series, volume=vol)
    assert app_client.delete(f"/volumes/{vol.id}").status_code == 204
    db.expire_all()
    assert db.get(Document, doc.id).volume_id is None


def test_assign_chapters(app_client, me, series, make_doc):
    vid = _volume(app_client, series).json()["id"]
    a, b = make_doc(me, series=series, order=1), make_doc(me, series=series, order=2)
    r = app_client.post(f"/volumes/{vid}/documents", json={"document_ids": [b.id, a.id]})
    assert r.status_code == 200
    assert [(d["id"], d["volume_id"]) for d in r.json()] == [(a.id, vid), (b.id, vid)]


@pytest.mark.parametrize("stray_owner", ["me", "other"])
def test_assign_refuses_strays_and_changes_nothing(
    app_client, db, me, make_user, make_series, series, make_doc, stray_owner
):
    vid = _volume(app_client, series).json()["id"]
    mine = make_doc(me, series=series)
    if stray_owner == "me":
        stray = make_doc(me, series=make_series(me, "Other"))
    else:
        stray = make_doc(make_user(email="other@example.com"))
    r = app_client.post(f"/volumes/{vid}/documents", json={"document_ids": [mine.id, stray.id]})
    assert r.status_code == 422
    db.expire_all()
    assert db.get(Document, mine.id).volume_id is None


def test_cover_upload_replaces_the_previous_one(app_client, db, me, make_doc):
    doc = make_doc(me, ["a"])
    for _ in range(2):
        r = app_client.put(
            f"/documents/{doc.id}/cover", files={"file": ("c.png", PNG, "image/png")}
        )
        assert r.status_code == 200
    covers = db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc.id)).all()
    assert [(c.is_cover, c.src_path, c.anchor_position) for c in covers] == [
        (True, "cover.png", 0)
    ]


def test_cover_must_really_be_an_image(app_client, me, make_doc):
    doc = make_doc(me)
    r = app_client.put(
        f"/documents/{doc.id}/cover", files={"file": ("c.png", b"<svg/>", "image/png")}
    )
    assert r.status_code == 415


def test_cover_size_is_capped(app_client, me, make_doc, monkeypatch):
    from api.routers import volumes

    monkeypatch.setattr(volumes, "MAX_IMAGE_BYTES", 8)
    doc = make_doc(me)
    r = app_client.put(f"/documents/{doc.id}/cover", files={"file": ("c.png", PNG, "image/png")})
    assert r.status_code == 413


def test_clear_cover_is_idempotent(app_client, db, me, make_doc):
    doc = make_doc(me)
    app_client.put(f"/documents/{doc.id}/cover", files={"file": ("c.png", PNG, "image/png")})
    assert app_client.delete(f"/documents/{doc.id}/cover").status_code == 204
    assert app_client.delete(f"/documents/{doc.id}/cover").status_code == 204
    assert db.scalars(select(DocumentImage).where(DocumentImage.document_id == doc.id)).all() == []


@pytest.fixture
def theirs(db, me, make_user, make_series, make_doc):
    other = make_user(email="other@example.com")
    series = make_series(other, "Theirs")
    volume = Volume(series_id=series.id, title="V")
    db.add(volume)
    db.flush()
    return {"series": series.id, "volume": volume.id, "doc": make_doc(other, ["x"]).id}


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("GET", "/series/{series}/volumes", {}),
        ("POST", "/series/{series}/volumes", {"json": {"title": "V2"}}),
        ("PATCH", "/volumes/{volume}", {"json": {"title": "x"}}),
        ("DELETE", "/volumes/{volume}", {}),
        ("POST", "/volumes/{volume}/documents", {"json": {"document_ids": [1]}}),
        ("PUT", "/documents/{doc}/cover", {"files": {"file": ("c.png", PNG, "image/png")}}),
        ("DELETE", "/documents/{doc}/cover", {}),
    ],
)
def test_another_users_objects_are_404(app_client, theirs, method, path, kwargs):
    assert app_client.request(method, path.format(**theirs), **kwargs).status_code == 404


def test_list_all_volumes_is_mine_only(app_client, db, me, make_user, make_series):
    s1, s2 = make_series(me, "A"), make_series(me, "B")
    theirs = make_series(make_user(email="other@example.com"), "Theirs")
    for s, title, order in [(s2, "B1", 1), (s1, "A2", 2), (s1, "A1", 1), (theirs, "X", 1)]:
        db.add(Volume(series_id=s.id, title=title, volume_order=order))
    db.flush()
    r = app_client.get("/volumes")
    assert r.status_code == 200
    assert [v["title"] for v in r.json()] == ["A1", "A2", "B1"]
