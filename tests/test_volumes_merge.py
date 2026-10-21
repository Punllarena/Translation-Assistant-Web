import pytest

from api.models import Document, Volume, VolumeSyosetuGroup
from tests import test_scrape_api as scrape_tests
from tests.test_scrape_api import _fetch, _marked_series, _placement

site = scrape_tests.site  # the fake-syosetu fixture


def _volume(client, series, title):
    r = client.post(f"/series/{series.id}/volumes", json={"kind": "", "subtitle": title})
    return r.json()["id"]


def _merge(client, series, ids, into):
    return client.post(f"/series/{series.id}/volumes/merge",
                       json={"volume_ids": ids, "into": into})


def _chapters(db, s):
    docs = db.query(Document).filter_by(series_id=s.id).order_by(Document.series_order).all()
    return [(d.series_order, d.title, d.volume_id) for d in docs]


@pytest.fixture
def plain(app_client, me, make_series, make_doc, db):
    """A plain series: V1 = [a, b], V2 = [c], V3 = [d, e]."""
    s = make_series(me, "Plain")
    v = [_volume(app_client, s, t) for t in ("V1", "V2", "V3")]
    for n, (title, vid) in enumerate(
            [("a", v[0]), ("b", v[0]), ("c", v[1]), ("d", v[2]), ("e", v[2])], start=1):
        make_doc(me, ["x"], series=s, order=n, title=title, volume=db.get(Volume, vid))
    db.flush()
    return s, v


def test_merge_moves_chapters_and_groups_and_deletes_the_others(app_client, plain, db):
    s, v = plain
    db.add(VolumeSyosetuGroup(series_id=s.id, volume_id=v[2], heading="H3"))
    db.flush()
    r = _merge(app_client, s, [v[1], v[2]], v[1])
    assert r.status_code == 200 and r.json()["id"] == v[1]
    db.expire_all()
    assert db.get(Volume, v[2]) is None
    assert [vid for _, _, vid in _chapters(db, s)] == [v[0], v[0], v[1], v[1], v[1]]
    assert db.query(VolumeSyosetuGroup).filter_by(series_id=s.id).one().volume_id == v[1]


def test_the_survivor_keeps_its_name_and_epub_fields(app_client, plain, db):
    s, v = plain
    app_client.patch(f"/volumes/{v[2]}", json={"epub_author": "Someone"})
    body = _merge(app_client, s, [v[0], v[2]], v[2]).json()
    assert (body["label"], body["epub_author"]) == ("V3", "Someone")


def test_merge_keeps_reading_order_in_a_plain_series(app_client, plain, db):
    s, v = plain
    _merge(app_client, s, [v[0], v[2]], v[2])
    db.expire_all()
    assert [(o, t) for o, t, _ in _chapters(db, s)] == [
        (1, "c"), (2, "a"), (3, "b"), (4, "d"), (5, "e")]


def test_merge_keeps_syosetu_numbers(app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me)
    _fetch(app_client, s, [1, 2, 3])
    ids = [v.id for v in db.query(Volume).filter_by(series_id=s.id).order_by(Volume.volume_order)]
    _merge(app_client, s, ids[:2], ids[0])
    db.expire_all()
    assert _placement(db, s) == [(1, "★ 一日"), (2, "★ 一日"), (3, "★ 二日")]


def test_a_later_fetch_of_a_merged_heading_lands_in_the_survivor(
        app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me)
    _fetch(app_client, s, [1, 2])
    ids = [v.id for v in db.query(Volume).filter_by(series_id=s.id).order_by(Volume.volume_order)]
    _merge(app_client, s, ids, ids[1])
    _merge_again = _volume(app_client, s, "Spare")
    _merge(app_client, s, [ids[1], _merge_again], ids[1])
    site[0]["https://ncode.syosetu.com/n1/"] = scrape_tests.MARKED.replace(
        '<div class="p-eplist__chapter-title">★ 二日</div>', "")
    _fetch(app_client, s, [3])
    db.expire_all()
    assert _placement(db, s) == [(1, "◇ 編"), (2, "◇ 編"), (3, "◇ 編")]


@pytest.mark.parametrize("case", ["one", "dupes", "into_outside", "foreign_volume"])
def test_bad_merges_are_422(app_client, me, make_series, plain, case):
    s, v = plain
    other = make_series(me, "Other")
    stray = _volume(app_client, other, "X")
    ids, into = {"one": ([v[0]], v[0]), "dupes": ([v[0], v[0]], v[0]),
                 "into_outside": ([v[0], v[1]], v[2]),
                 "foreign_volume": ([v[0], stray], v[0])}[case]
    assert _merge(app_client, s, ids, into).status_code == 422


def test_merge_in_another_users_series_is_404(app_client, me, make_user, make_series):
    theirs = make_series(make_user(email="o@example.com"), "T")
    assert _merge(app_client, theirs, [1, 2], 1).status_code == 404


def test_merge_is_409_while_a_fetch_runs(app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me)
    _fetch(app_client, s, [1, 2])
    ids = [v.id for v in db.query(Volume).filter_by(series_id=s.id)]
    app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [3]})
    assert _merge(app_client, s, ids, ids[0]).status_code == 409
