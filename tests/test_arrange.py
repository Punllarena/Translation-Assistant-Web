from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from api.models import Document, Volume


@pytest.fixture
def lib(db, me, make_series, make_doc):
    series = make_series(me)
    va = Volume(series_id=series.id, title="A", volume_order=1)
    vb = Volume(series_id=series.id, title="B", volume_order=2)
    db.add_all([va, vb])
    db.flush()
    d = {
        "a1": make_doc(me, series=series, volume=va, order=1, title="a1"),
        "a2": make_doc(me, series=series, volume=va, order=2, title="a2"),
        "b1": make_doc(me, series=series, volume=vb, order=3, title="b1"),
    }
    return series, va, vb, d


def _orders(db, d):
    db.expire_all()
    return {k: db.get(Document, v.id).series_order for k, v in d.items()}


def test_assigning_to_a_volume_appends_and_renumbers(app_client, db, lib):
    series, va, vb, d = lib
    r = app_client.post(f"/volumes/{va.id}/documents", json={"document_ids": [d["b1"].id]})
    assert r.status_code == 200
    assert _orders(db, d) == {"a1": 1, "a2": 2, "b1": 3}
    assert db.get(Document, d["b1"].id).volume_id == va.id


def test_reorder_inside_a_volume_keeps_volumes_contiguous(app_client, db, lib):
    series, va, vb, d = lib
    ids = [d["b1"].id, d["a2"].id, d["a1"].id]
    r = app_client.put(f"/series/{series.id}/order", json={"document_ids": ids})
    assert r.status_code == 200
    assert _orders(db, d) == {"a2": 1, "a1": 2, "b1": 3}


def test_loose_chapters_follow_the_last_volume(app_client, db, me, make_doc, lib):
    series, va, vb, d = lib
    for doc, order in ((d["a1"], 2), (d["a2"], 3), (d["b1"], 4)):
        doc.series_order = order
    x = make_doc(me, series=series, order=1, title="x")
    d["x"] = x
    db.flush()
    ids = [x.id, d["a1"].id, d["a2"].id, d["b1"].id]
    app_client.put(f"/series/{series.id}/order", json={"document_ids": ids})
    assert _orders(db, d) == {"a1": 1, "a2": 2, "b1": 3, "x": 4}


def test_new_chapter_in_a_volume_lands_at_its_end(app_client, db, lib):
    series, va, vb, d = lib
    r = app_client.post(
        "/documents", json={"title": "new", "series_id": series.id, "volume_id": va.id}
    )
    assert r.status_code == 201
    d["new"] = db.get(Document, r.json()["id"])
    assert _orders(db, d) == {"a1": 1, "a2": 2, "new": 3, "b1": 4}


def test_deleting_a_volume_moves_its_chapters_after_the_rest(app_client, db, lib):
    series, va, vb, d = lib
    assert app_client.delete(f"/volumes/{va.id}").status_code == 204
    assert _orders(db, d) == {"b1": 1, "a1": 2, "a2": 3}


def test_changing_volume_order_rearranges(app_client, db, lib):
    series, va, vb, d = lib
    r = app_client.patch(f"/volumes/{vb.id}", json={"volume_order": 0})
    assert r.status_code == 200
    assert _orders(db, d) == {"b1": 1, "a1": 2, "a2": 3}


def test_syosetu_series_keeps_its_numbers(app_client, db, me, make_series, make_doc):
    series = make_series(me, "Syo")
    series.syosetu_url = "https://ncode.syosetu.com/n0000a/"
    vol = Volume(series_id=series.id, title="V", volume_order=1)
    db.add(vol)
    db.flush()
    d = {
        "x": make_doc(me, series=series, order=5, title="x"),
        "y": make_doc(me, series=series, order=9, title="y"),
    }
    ids = [d["y"].id, d["x"].id]
    r = app_client.put(f"/series/{series.id}/order", json={"document_ids": ids})
    assert r.status_code == 409
    assert app_client.post(f"/series/{series.id}/renumber").status_code == 409
    r = app_client.post(f"/volumes/{vol.id}/documents", json={"document_ids": ids})
    assert r.status_code == 200
    assert _orders(db, d) == {"x": 5, "y": 9}
    assert all(db.get(Document, v.id).volume_id == vol.id for v in d.values())
    assert db.scalar(select(Document.series_order).where(Document.id == d["x"].id)) == 5


def test_volume_only_patch_sends_the_chapter_to_the_end_of_that_volume(app_client, db, lib):
    series, va, vb, d = lib
    r = app_client.patch(f"/documents/{d['a1'].id}", json={"volume_id": vb.id})
    assert r.status_code == 200
    assert _orders(db, d) == {"a2": 1, "b1": 2, "a1": 3}
    assert db.get(Document, d["a1"].id).volume_id == vb.id


def _syosetu(db, me, make_series, make_doc):
    series = make_series(me, "Syo")
    series.syosetu_url = "https://ncode.syosetu.com/n0000a/"
    db.flush()
    d = {
        "x": make_doc(me, ["l1", "l2"], series=series, order=5, title="x"),
        "y": make_doc(me, ["m1"], series=series, order=9, title="y"),
        "z": make_doc(me, ["n1"], series=series, order=12, title="z"),
    }
    return series, d


def test_syosetu_split_keeps_numbers_and_new_segment_shares_the_original(
    app_client, db, me, make_series, make_doc
):
    series, d = _syosetu(db, me, make_series, make_doc)
    cuts = {"cuts": [{"start": 1, "title": "x2"}]}
    r = app_client.post(f"/documents/{d['x'].id}/split", json=cuts)
    assert r.status_code == 200
    new_id = r.json()[1]["id"]
    assert _orders(db, d) == {"x": 5, "y": 9, "z": 12}
    assert db.get(Document, new_id).series_order == 5


def test_syosetu_merge_leaves_the_remaining_numbers(app_client, db, me, make_series, make_doc):
    series, d = _syosetu(db, me, make_series, make_doc)
    r = app_client.post(
        "/documents/merge", json={"document_ids": [d["x"].id, d["y"].id], "title": "xy"}
    )
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Document, d["x"].id).series_order == 5
    assert db.get(Document, d["z"].id).series_order == 12


def test_merge_in_a_series_with_volumes_keeps_volumes_contiguous(app_client, db, lib):
    series, va, vb, d = lib
    r = app_client.post(
        "/documents/merge", json={"document_ids": [d["a1"].id, d["a2"].id], "title": "a"}
    )
    assert r.status_code == 200
    db.expire_all()
    assert db.get(Document, d["a1"].id).series_order == 1
    assert db.get(Document, d["b1"].id).series_order == 2


def test_split_in_a_series_with_volumes_keeps_volumes_contiguous(
    app_client, db, me, make_doc, lib
):
    series, va, vb, d = lib
    doc = make_doc(me, ["l1", "l2"], series=series, volume=va, order=1, title="s")
    d["s"] = doc
    for key, order in (("a1", 2), ("a2", 3), ("b1", 4)):
        d[key].series_order = order
    db.flush()
    r = app_client.post(f"/documents/{doc.id}/split", json={"cuts": [{"start": 1, "title": "s2"}]})
    assert r.status_code == 200
    new_id = r.json()[1]["id"]
    db.expire_all()
    order = {k: db.get(Document, v.id).series_order for k, v in d.items()}
    order["s2"] = db.get(Document, new_id).series_order
    assert order == {"s": 1, "s2": 2, "a1": 3, "a2": 4, "b1": 5}


OLD = datetime(2020, 1, 1, tzinfo=UTC)


def _age(db, d):
    for doc in d.values():
        doc.updated_at = OLD
    db.flush()


def _stamps(db, d):
    db.expire_all()
    return {k: db.get(Document, v.id).updated_at for k, v in d.items()}


def test_renumbering_after_a_move_leaves_other_chapters_updated_at(app_client, db, lib):
    series, va, vb, d = lib
    _age(db, d)
    r = app_client.patch(f"/documents/{d['a1'].id}", json={"volume_id": vb.id})
    assert r.status_code == 200
    assert _orders(db, d) == {"a2": 1, "b1": 2, "a1": 3}
    stamps = _stamps(db, d)
    assert stamps["a2"] == OLD and stamps["b1"] == OLD


def test_renumber_by_title_leaves_updated_at(app_client, db, lib):
    series, va, vb, d = lib
    d["a1"].series_order, d["a2"].series_order = 2, 1
    _age(db, d)
    assert app_client.post(f"/series/{series.id}/renumber").status_code == 200
    assert _orders(db, d) == {"a1": 1, "a2": 2, "b1": 3}
    assert set(_stamps(db, d).values()) == {OLD}


def test_deleting_a_chapter_renumbers_the_rest(app_client, db, lib):
    series, va, vb, d = lib
    assert app_client.delete(f"/documents/{d['a1'].id}").status_code == 204
    del d["a1"]
    assert _orders(db, d) == {"a2": 1, "b1": 2}
