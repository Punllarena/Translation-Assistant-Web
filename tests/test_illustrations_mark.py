import pytest

from api.models import Document, DocumentImage, Volume


def _vol(db, series, order, name):
    v = Volume(series_id=series.id, subtitle=name, volume_order=order)
    db.add(v)
    db.flush()
    return v


@pytest.fixture
def lib(db, me, make_series, make_doc):
    """V1 = [a, b, c] (a, b text-free), V2 = [d] ; text chapter t in V1."""
    s = make_series(me, "Lib")
    v1, v2 = _vol(db, s, 1, "V1"), _vol(db, s, 2, "V2")
    d = {
        "a": make_doc(me, [], series=s, volume=v1, order=1, title="a"),
        "b": make_doc(me, [], series=s, volume=v1, order=2, title="b"),
        "t": make_doc(me, ["some text"], series=s, volume=v1, order=3, title="t"),
        "d": make_doc(me, [], series=s, volume=v2, order=4, title="d"),
    }
    db.flush()
    return s, v1, v2, d


def _mark(client, doc, value=True):
    return client.patch(f"/documents/{doc.id}", json={"is_illustrations": value})


def _row(client, doc):
    return next(r for r in client.get("/documents").json() if r["id"] == doc.id)


def test_mark_moves_it_first_and_unmark_keeps_it_there(app_client, db, lib):
    s, v1, v2, d = lib
    assert _mark(app_client, d["b"]).status_code == 200
    db.expire_all()
    assert db.get(Document, d["b"].id).series_order == 1
    row = _row(app_client, d["b"])
    assert row["chapter_number"] is None and row["is_illustrations"]
    assert _mark(app_client, d["b"], False).status_code == 200
    db.expire_all()
    assert db.get(Document, d["b"].id).series_order == 1
    assert _row(app_client, d["b"])["chapter_number"] == 1


def test_mark_refusals(app_client, db, me, make_series, make_doc, lib):
    s, v1, v2, d = lib
    r = _mark(app_client, d["t"])
    assert (r.status_code, r.json()["detail"]) == (
        409, "only a chapter with no text can be the Illustrations chapter")
    loose = make_doc(me, [], series=s, order=9, title="loose")
    r = _mark(app_client, loose)
    assert (r.status_code, r.json()["detail"]) == (409, "put the chapter in a volume first")
    assert _mark(app_client, d["a"]).status_code == 200
    r = _mark(app_client, d["b"])
    assert (r.status_code, r.json()["detail"]) == (
        409, "this volume already has an Illustrations chapter")
    syo = make_series(me, "Syo")
    syo.syosetu_url = "https://ncode.syosetu.com/n1/"
    sv = _vol(db, syo, 1, "SV")
    sd = make_doc(me, [], series=syo, volume=sv, order=1, title="sd")
    db.flush()
    r = _mark(app_client, sd)
    assert (r.status_code, r.json()["detail"]) == (
        409, "a syosetu series has no Illustrations chapter")


def test_merge_with_text_into_illustrations_is_refused(app_client, db, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["a"])
    r = app_client.post("/documents/merge", json={
        "document_ids": [d["a"].id, d["t"].id], "title": "m"})
    assert r.status_code == 409


def test_merge_image_only_chapters_into_it_keeps_the_mark(app_client, db, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["b"])  # not the lowest series_order after a (b is first now) -> re-order
    db.expire_all()
    # make the marked one not the lowest series_order among the merged documents
    a = db.get(Document, d["a"].id)
    marked = db.get(Document, d["b"].id)
    assert marked.series_order < a.series_order
    r = app_client.post("/documents/merge", json={
        "document_ids": [a.id, marked.id], "title": "m"})
    assert r.status_code == 200
    assert r.json()["id"] == marked.id and r.json()["is_illustrations"]
    db.expire_all()
    assert db.get(Document, a.id) is None
    assert db.get(Document, marked.id).series_order == 1


def test_merge_survivor_is_the_marked_one_even_when_later(app_client, db, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["d"])  # V2's, first in V2, series_order after V1's chapters
    r = app_client.post("/documents/merge", json={
        "document_ids": [d["a"].id, d["d"].id], "title": "m"})
    assert r.status_code == 200
    assert r.json()["id"] == d["d"].id and r.json()["is_illustrations"]


def test_edit_source_with_text_is_refused(app_client, db, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["a"])
    r = app_client.put(f"/documents/{d['a'].id}/source", json={"text": "hello"})
    assert r.status_code == 409
    assert "can't hold text" in r.json()["detail"]


def test_move_rules(app_client, db, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["a"])
    r = app_client.patch(f"/documents/{d['a'].id}", json={"volume_id": None})
    assert r.status_code == 409
    assert r.json()["detail"] == "the Illustrations chapter must stay in a volume"
    _mark(app_client, d["d"])
    r = app_client.post(f"/volumes/{v2.id}/documents", json={"document_ids": [d["a"].id]})
    assert r.status_code == 409
    assert r.json()["detail"] == "this volume already has an Illustrations chapter"
    _mark(app_client, d["d"], False)
    r = app_client.post(f"/volumes/{v2.id}/documents", json={"document_ids": [d["a"].id]})
    assert r.status_code == 200
    db.expire_all()
    first = (db.query(Document).filter_by(volume_id=v2.id)
             .order_by(Document.series_order).first())
    assert first.id == d["a"].id


def test_deleting_its_volume_unmarks_it(app_client, db, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["a"])
    assert app_client.delete(f"/volumes/{v1.id}").status_code == 204
    db.expire_all()
    a = db.get(Document, d["a"].id)
    assert a.volume_id is None and not a.is_illustrations


def _pics(db, doc, *names):
    for name in names:
        db.add(DocumentImage(document_id=doc.id, anchor_position=0, is_cover=False,
                             src_path=name, data=name.encode()))
    db.flush()


def _held(db, doc_id):
    rows = db.query(DocumentImage).filter_by(document_id=doc_id)
    return [im.src_path for im in rows.order_by(DocumentImage.anchor_position, DocumentImage.id)]


def _merge(client, s, ids, into):
    return client.post(f"/series/{s.id}/volumes/merge", json={"volume_ids": ids, "into": into})


def test_volume_merge_keeps_one_illustrations_chapter(app_client, db, me, make_doc, lib):
    s, v1, v2, d = lib
    v3 = _vol(db, s, 3, "V3")
    e = make_doc(me, [], series=s, volume=v3, order=5, title="e")
    db.flush()
    for doc in (d["a"], d["d"], e):
        assert _mark(app_client, doc).status_code == 200
    _pics(db, e, "e1")
    _pics(db, d["a"], "x", "e1", "y")  # e1 is already held: dropped
    _pics(db, d["d"], "y", "z")

    # into's own wins; the others' images follow its own, by volume_order, and they go
    assert _merge(app_client, s, [v1.id, v2.id, v3.id], v3.id).status_code == 200
    db.expire_all()
    docs = db.query(Document).filter_by(series_id=s.id).all()
    assert [x.id for x in docs if x.is_illustrations] == [e.id]
    assert {x.id for x in docs} == {e.id, d["b"].id, d["t"].id}
    assert _held(db, e.id) == ["e1", "x", "y", "z"]
    assert db.query(DocumentImage).filter(
        DocumentImage.document_id.in_([d["a"].id, d["d"].id])).count() == 0


def test_volume_merge_without_into_mark_keeps_first_by_volume_order(
        app_client, db, me, make_doc, lib):
    s, v1, v2, d = lib
    v3 = _vol(db, s, 3, "V3")
    make_doc(me, [], series=s, volume=v3, order=5, title="e")
    db.flush()
    for doc in (d["a"], d["d"]):
        _mark(app_client, doc)
    _pics(db, d["a"], "a1")
    _pics(db, d["d"], "d1")
    r = _merge(app_client, s, [v1.id, v2.id, v3.id], v3.id)
    assert r.status_code == 200
    db.expire_all()
    marked = [x.id for x in db.query(Document).filter_by(series_id=s.id)
              if x.is_illustrations]
    assert marked == [d["a"].id]
    assert db.get(Document, d["d"].id) is None
    assert _held(db, d["a"].id) == ["a1", "d1"]


def test_volume_merge_keeps_text_chapter_numbers(app_client, db, me, make_doc, make_series):
    s = make_series(me, "Numbers")
    v1, v2 = _vol(db, s, 1, "V1"), _vol(db, s, 2, "V2")
    i1 = make_doc(me, [], series=s, volume=v1, order=1, title="i1")
    make_doc(me, ["one"], series=s, volume=v1, order=2, title="c1")
    make_doc(me, ["two"], series=s, volume=v1, order=3, title="c2")
    i2 = make_doc(me, [], series=s, volume=v2, order=4, title="i2")
    make_doc(me, ["three"], series=s, volume=v2, order=5, title="c3")
    db.flush()
    for doc in (i1, i2):
        assert _mark(app_client, doc).status_code == 200
    _pics(db, i2, "plate")

    def numbers():
        rows = [r for r in app_client.get("/documents").json() if r["series_id"] == s.id]
        return {r["title"]: r["chapter_number"] for r in rows if not r["is_illustrations"]}

    before = numbers()
    assert before == {"c1": 1, "c2": 2, "c3": 3}
    assert _merge(app_client, s, [v1.id, v2.id], v1.id).status_code == 200
    assert numbers() == before


def test_a_marked_chapter_cannot_move_to_a_syosetu_series(app_client, db, me, make_series, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["a"])
    web = make_series(me, "Web")
    web.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    r = app_client.patch(f"/documents/{d['a'].id}", json={"series_id": web.id})
    assert r.status_code == 409
    assert r.json()["detail"] == "a syosetu series has no Illustrations chapter"


def test_becoming_a_syosetu_series_unmarks_it(app_client, db, lib):
    s, v1, v2, d = lib
    _mark(app_client, d["a"])
    r = app_client.patch(f"/series/{s.id}", json={"syosetu_url": "https://ncode.syosetu.com/n2/"})
    assert r.status_code == 200
    db.expire_all()
    assert not db.get(Document, d["a"].id).is_illustrations
