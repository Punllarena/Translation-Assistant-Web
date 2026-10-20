import pytest
from sqlalchemy import select

from api.models import DocumentImage, Line, Volume


def _lines(db, doc_id):
    db.expire_all()
    rows = db.scalars(select(Line).where(Line.document_id == doc_id).order_by(Line.line_number))
    return [(ln.prefix, ln.raw_text) for ln in rows]


def test_documents_require_authentication(app_client):
    assert app_client.get("/documents").status_code == 401


def test_create_empty_document(app_client, me, make_series):
    series = make_series(me)
    r = app_client.post("/documents", json={"title": "Notes", "series_id": series.id})
    assert r.status_code == 201
    assert (r.json()["series_id"], r.json()["series_order"]) == (series.id, 1)


def test_create_from_raw_text_splits_sentences(app_client, db, me, make_series):
    body = {"title": "Ch1", "series_id": make_series(me).id, "raw_text": "一文目。二文目。\n\n次"}
    r = app_client.post("/documents", json=body)
    assert _lines(db, r.json()["id"]) == [
        ("%", "一文目。"), ("$", "二文目。"), ("%", ""), ("%", "次"),
    ]


def test_create_in_series_appends(app_client, me, make_series, make_doc):
    series = make_series(me)
    make_doc(me, series=series, order=3)
    r = app_client.post("/documents", json={"title": "Next", "series_id": series.id})
    assert r.json()["series_order"] == 4


def test_volume_must_belong_to_the_named_series(app_client, db, me, make_series):
    a, b = make_series(me, "A"), make_series(me, "B")
    vol = Volume(series_id=b.id, title="V")
    db.add(vol)
    db.flush()
    wrong = app_client.post(
        "/documents", json={"title": "x", "series_id": a.id, "volume_id": vol.id}
    )
    no_series = app_client.post("/documents", json={"title": "x", "volume_id": vol.id})
    assert wrong.status_code == no_series.status_code == 422


def test_foreign_series_reads_exactly_like_a_missing_one(app_client, me, make_user, make_series):
    theirs = make_series(make_user(email="other@example.com"))
    foreign = app_client.post("/documents", json={"title": "x", "series_id": theirs.id})
    missing = app_client.post("/documents", json={"title": "x", "series_id": 999999})
    assert foreign.status_code == missing.status_code == 422
    assert foreign.json() == missing.json()


def test_list_reports_progress_and_only_mine(app_client, db, me, make_user, make_doc):
    half = make_doc(me, ["a", "b"], title="Half", translated=False)
    half.lines[0].translated_text = "A"
    make_doc(me, ["a", "", "b"], title="Blanks ignored")
    pictures = make_doc(me, [], title="Pictures")
    db.add(DocumentImage(document_id=pictures.id, src_path="p.png", data=b"x", is_cover=True))
    make_doc(make_user(email="other@example.com"), ["z"], title="Theirs")
    db.flush()
    rows = {d["title"]: d for d in app_client.get("/documents").json()}
    assert set(rows) == {"Half", "Blanks ignored", "Pictures"}
    assert (rows["Half"]["progress"], rows["Half"]["line_count"]) == (50, 2)
    assert rows["Blanks ignored"]["progress"] == 100
    assert (rows["Pictures"]["progress"], rows["Pictures"]["has_cover"]) == (100, True)


def test_moving_series_appends_and_leaves_volume(app_client, db, me, make_series, make_doc):
    a, b = make_series(me, "A"), make_series(me, "B")
    vol = Volume(series_id=a.id, title="V")
    db.add(vol)
    db.flush()
    make_doc(me, series=b, order=7)
    doc = make_doc(me, series=a, order=1, volume=vol)
    body = app_client.patch(f"/documents/{doc.id}", json={"series_id": b.id}).json()
    assert (body["series_id"], body["series_order"], body["volume_id"]) == (b.id, 8, None)


def test_patch_volume_of_another_series_is_422(app_client, db, me, make_series, make_doc):
    a, b = make_series(me, "A"), make_series(me, "B")
    vol = Volume(series_id=b.id, title="V")
    db.add(vol)
    db.flush()
    doc = make_doc(me, series=a)
    assert app_client.patch(f"/documents/{doc.id}", json={"volume_id": vol.id}).status_code == 422


def test_patch_null_title_is_422(app_client, me, make_doc):
    doc = make_doc(me)
    assert app_client.patch(f"/documents/{doc.id}", json={"title": None}).status_code == 422


def test_delete_removes_document_and_lines(app_client, db, me, make_doc):
    doc = make_doc(me, ["a"])
    assert app_client.delete(f"/documents/{doc.id}").status_code == 204
    assert app_client.get(f"/documents/{doc.id}").status_code == 404
    assert _lines(db, doc.id) == []


@pytest.mark.parametrize(
    ("method", "kwargs"), [("get", {}), ("patch", {"json": {"title": "x"}}), ("delete", {})]
)
def test_another_users_document_is_404(app_client, me, make_user, make_doc, method, kwargs):
    theirs = make_doc(make_user(email="other@example.com"), ["x"])
    assert getattr(app_client, method)(f"/documents/{theirs.id}", **kwargs).status_code == 404


def test_create_line_count_is_capped(app_client, me, make_series, monkeypatch):
    from api import library

    monkeypatch.setattr(library, "MAX_LINES", 2)
    body = {"title": "Big", "series_id": make_series(me).id, "raw_text": "a\nb\nc"}
    r = app_client.post("/documents", json=body)
    assert (r.status_code, r.json()["detail"]) == (422, "too many lines (max 2)")
    assert app_client.get("/documents").json() == []


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("patch", "/documents/1", {"last_position": 2**31}),
        ("patch", "/series/1", {"wp_unlock_after": 2**31}),
        ("post", "/series/1/volumes", {"title": "V", "volume_order": 2**31}),
    ],
)
def test_integer_fields_are_bounded(app_client, me, method, path, body):
    assert getattr(app_client, method)(path, json=body).status_code == 422
