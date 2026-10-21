"""Volume placement by kind and index, drag reorder and Sort by number."""

import pytest

from api.models import Document, Volume


@pytest.fixture
def series(me, make_series):
    return make_series(me, "Mushoku")


def _new(client, series, kind="Volume", index=None, **body):
    if index is not None:
        body["volume_index"] = str(index)
    r = client.post(f"/series/{series.id}/volumes", json={"kind": kind, **body})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _labels(client, series):
    r = client.get(f"/series/{series.id}/volumes")
    return [v["label"] for v in r.json()]


def _ids(client, series):
    return [v["id"] for v in client.get(f"/series/{series.id}/volumes").json()]


def _put(client, series, ids):
    return client.put(f"/series/{series.id}/volumes/order", json={"volume_ids": ids})


def test_new_volume_goes_after_its_kind(app_client, series):
    v1, v2, v3 = (_new(app_client, series, index=i) for i in (1, 2, 3))
    ss1 = _new(app_client, series, "Side Story", 1)
    assert _labels(app_client, series) == ["Volume 1", "Volume 2", "Volume 3", "Side Story 1"]
    v4 = _new(app_client, series, index=4)
    assert _labels(app_client, series)[3:] == ["Volume 4", "Side Story 1"]
    assert _put(app_client, series, [v1, v2, v3, ss1, v4]).status_code == 200
    _new(app_client, series, index=5)
    _new(app_client, series, "Side Story", 2)
    assert _labels(app_client, series) == [
        "Volume 1", "Volume 2", "Volume 3", "Side Story 1", "Side Story 2", "Volume 4",
        "Volume 5",
    ]


def test_first_of_kind_uses_sort_key(app_client, series):
    _new(app_client, series, index=1)
    _new(app_client, series, index=2)
    _new(app_client, series, "Extra", subtitle="E")
    assert _labels(app_client, series)[-1].startswith("Extra")
    _new(app_client, series, "", subtitle="Prologue")
    labels = _labels(app_client, series)
    assert labels[-1] == "Prologue" and labels[-2].startswith("Extra")


def test_unnumbered_goes_after_existing_unnumbered_of_kind(app_client, series):
    _new(app_client, series, "Extra", subtitle="A")
    _new(app_client, series, "Extra", subtitle="B")
    assert [v.split("·")[-1].strip() for v in _labels(app_client, series)] == ["A", "B"]


def test_index_edit_moves_only_that_volume(app_client, series):
    v1 = _new(app_client, series, index=1)
    ss1 = _new(app_client, series, "Side Story", 1)
    v2 = _new(app_client, series, index=2)
    v3 = _new(app_client, series, index=3)
    assert _put(app_client, series, [ss1, v1, v2, v3]).status_code == 200
    r = app_client.patch(f"/volumes/{v3}", json={"volume_index": "1.5"})
    assert r.status_code == 200
    assert _labels(app_client, series) == ["Side Story 1", "Volume 1", "Volume 1.5", "Volume 2"]


def test_patch_without_name_change_does_not_move(app_client, series):
    v1 = _new(app_client, series, index=1)
    v2 = _new(app_client, series, index=2)
    assert _put(app_client, series, [v2, v1]).status_code == 200
    assert app_client.patch(f"/volumes/{v1}", json={"epub_author": "X"}).status_code == 200
    assert _labels(app_client, series) == ["Volume 2", "Volume 1"]


def test_explicit_volume_order_on_create_still_wins(app_client, series):
    _new(app_client, series, index=1)
    _new(app_client, series, index=2)
    _new(app_client, series, index=3, volume_order=0)
    assert _labels(app_client, series)[0] == "Volume 3"


def test_reorder_stale_list_422(app_client, series):
    a = _new(app_client, series, index=1)
    b = _new(app_client, series, index=2)
    assert _put(app_client, series, [b]).status_code == 422
    assert _put(app_client, series, [b, b, a]).status_code == 422
    assert _labels(app_client, series) == ["Volume 1", "Volume 2"]


def test_sort_by_number(app_client, series):
    pro = _new(app_client, series, "", subtitle="Prologue")
    e = _new(app_client, series, "Extra", subtitle="E")
    v2 = _new(app_client, series, index=2)
    ss = _new(app_client, series, "Side Story", 1)
    v1 = _new(app_client, series, index=1)
    assert _put(app_client, series, [pro, ss, e, v2, v1]).status_code == 200
    r = app_client.post(f"/series/{series.id}/volumes/sort")
    assert r.status_code == 200
    assert [v["id"] for v in r.json()] == [v1, v2, e, ss, pro]
    assert _ids(app_client, series) == [v1, v2, e, ss, pro]


def test_reorder_and_sort_rearrange_chapters(app_client, db, me, series, make_doc):
    a = _new(app_client, series, index=1)
    b = _new(app_client, series, index=2)
    da = make_doc(me, series=series, title="a", order=1, volume=db.get(Volume, a))
    dbb = make_doc(me, series=series, title="b", order=2, volume=db.get(Volume, b))
    assert _put(app_client, series, [b, a]).status_code == 200
    db.expire_all()
    assert (db.get(Document, dbb.id).series_order, db.get(Document, da.id).series_order) == (1, 2)
    assert app_client.post(f"/series/{series.id}/volumes/sort").status_code == 200
    db.expire_all()
    assert (db.get(Document, da.id).series_order, db.get(Document, dbb.id).series_order) == (1, 2)


def test_reorder_other_users_series_404(app_client, me, make_user, make_series):
    other = make_series(make_user(email="o@example.com"), "Theirs")
    assert _put(app_client, other, [1]).status_code == 404
    assert app_client.post(f"/series/{other.id}/volumes/sort").status_code == 404
