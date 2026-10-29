import pytest

from api.models import Volume
from tests import test_scrape_api as scrape_tests
from tests.test_scrape_api import MARKED, _fetch, _grouped_series, _marked_series, _placement

site = scrape_tests.site  # the fake-syosetu fixture

INDEX_URL = "https://ncode.syosetu.com/n1/"


def _regroup(app_client, s, mode, marker="", apply=False):
    return app_client.post(f"/series/{s.id}/syosetu/volume-headings",
                           json={"mode": mode, "marker": marker, "apply": apply})


def _all_fetched(app_client, make_series, site, db, me):
    s = _marked_series(make_series, site, db, me)
    _fetch(app_client, s, [1, 2, 3])
    return s


def _vol(db, s, title):
    return db.query(Volume).filter_by(series_id=s.id, kind="", subtitle=title).one()


def test_preview_changes_nothing_but_the_sequence(app_client, me, make_series, site, db):
    s = _all_fetched(app_client, make_series, site, db, me)
    before = _placement(db, s)
    r = _regroup(app_client, s, "marker", "★")
    assert r.status_code == 200
    assert r.json() == {"volumes_created": 0, "chapters_moved": 1, "volumes_emptied": 1}
    db.expire_all()
    assert _placement(db, s) == before and s.syosetu_volume_mode == "all"


def test_apply_switches_to_marker_and_keeps_emptied_volumes(
        app_client, me, make_series, site, db):
    s = _all_fetched(app_client, make_series, site, db, me)
    r = _regroup(app_client, s, "marker", "★", apply=True)
    assert r.json() == {"volumes_created": 0, "chapters_moved": 1, "volumes_emptied": 1}
    db.expire_all()
    assert _placement(db, s) == [(1, "★ 一日"), (2, "★ 一日"), (3, "★ 二日")]
    assert _vol(db, s, "◇ 編") is not None
    assert (s.syosetu_volume_mode, s.syosetu_volume_marker) == ("marker", "★")


def test_switching_back_reuses_the_renamed_volume(app_client, me, make_series, site, db):
    s = _all_fetched(app_client, make_series, site, db, me)
    _regroup(app_client, s, "marker", "★", apply=True)
    app_client.patch(f"/volumes/{_vol(db, s, '◇ 編').id}", json={"subtitle": "Arc"})
    r = _regroup(app_client, s, "all", apply=True)
    assert r.json()["volumes_created"] == 0
    db.expire_all()
    assert _placement(db, s)[1] == (2, "Arc")


def test_marker_mode_creates_missing_volumes(app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me, "off")
    _fetch(app_client, s, [1, 2, 3])
    r = _regroup(app_client, s, "marker", "★", apply=True)
    assert r.json() == {"volumes_created": 2, "chapters_moved": 3, "volumes_emptied": 0}
    db.expire_all()
    assert _placement(db, s) == [(1, "★ 一日"), (2, "★ 一日"), (3, "★ 二日")]


def test_regroup_leaves_hand_made_volumes_and_headingless_chapters(
        app_client, me, make_series, site, db):
    s = _grouped_series(make_series, site, db, me)
    _fetch(app_client, s, [1, 2, 3])
    mine = app_client.post(f"/series/{s.id}/volumes", json={"kind": "", "subtitle": "Mine"}).json()
    ch3 = [d for d in s.documents if d.series_order == 3][0]
    app_client.post(f"/volumes/{mine['id']}/documents", json={"document_ids": [ch3.id]})
    r = _regroup(app_client, s, "off", apply=True)
    assert r.json()["chapters_moved"] == 1
    db.expire_all()
    assert _placement(db, s) == [(1, None), (2, None), (3, "Mine")]


def test_regroup_reads_the_index_once_when_no_sequence_is_stored(
        app_client, me, make_series, make_doc, site, db):
    pages, calls = site
    pages[INDEX_URL] = MARKED
    s = make_series(me, "S")
    s.syosetu_url = INDEX_URL
    for n in (1, 2, 3):
        make_doc(me, ["x"], series=s, order=n).source_url = f"{INDEX_URL}{n}/"
    db.flush()
    assert _regroup(app_client, s, "marker", "★").json() == {
        "volumes_created": 2, "chapters_moved": 3, "volumes_emptied": 0}
    _regroup(app_client, s, "marker", "★", apply=True)
    assert calls.count(INDEX_URL) == 1
    db.expire_all()
    assert _placement(db, s) == [(1, "★ 一日"), (2, "★ 一日"), (3, "★ 二日")]


def test_off_sends_heading_chapters_to_no_volume(app_client, me, make_series, site, db):
    s = _all_fetched(app_client, make_series, site, db, me)
    r = _regroup(app_client, s, "off", apply=True)
    assert r.json() == {"volumes_created": 0, "chapters_moved": 3, "volumes_emptied": 3}
    db.expire_all()
    assert _placement(db, s) == [(1, None), (2, None), (3, None)]
    assert db.query(Volume).filter_by(series_id=s.id).count() == 3


@pytest.mark.parametrize("body", [
    {"mode": "marker", "marker": ""}, {"mode": "marker", "marker": "あ"},
    {"mode": "all", "marker": "★"}, {"mode": "x"}, {"mode": "marker", "marker": "★★"},
])
def test_bad_settings_are_422(app_client, me, make_series, site, db, body):
    s = _all_fetched(app_client, make_series, site, db, me)
    r = app_client.post(f"/series/{s.id}/syosetu/volume-headings", json=body)
    assert r.status_code == 422


def test_regroup_is_409_while_a_fetch_runs(app_client, me, make_series, site, db):
    s = _marked_series(make_series, site, db, me)
    app_client.post(f"/series/{s.id}/syosetu/fetch", json={"nums": [1]})
    assert _regroup(app_client, s, "off").status_code == 409


def test_regroup_needs_your_series_with_a_url(app_client, me, make_series, make_user, site):
    mine = make_series(me, "No URL")
    assert _regroup(app_client, mine, "off").status_code == 422
    theirs = make_series(make_user(email="o@example.com"), "T")
    assert _regroup(app_client, theirs, "off").status_code == 404


def test_regroup_leaves_chapters_not_fetched_from_syosetu(
        app_client, me, make_series, make_doc, site, db):
    s = _all_fetched(app_client, make_series, site, db, me)
    make_doc(me, ["note"], series=s, order=4, title="Translator's note")
    db.flush()
    r = _regroup(app_client, s, "marker", "★", apply=True)
    assert r.json()["chapters_moved"] == 1
    db.expire_all()
    assert _placement(db, s)[3] == (4, None)


def test_regroup_moves_imported_chapters_that_have_no_url(
        app_client, me, make_series, make_doc, site, db):
    # ta.db imports carry no source_url; the fetch job already treats their numbers as
    # syosetu's (it skips them), so regroup must place them too
    s = _marked_series(make_series, site, db, me)
    for n in (1, 2):
        make_doc(me, ["x"], series=s, order=n)
    make_doc(me, ["note"], series=s, order=0, title="Synopsis")
    db.flush()
    _fetch(app_client, s, [3])
    r = _regroup(app_client, s, "marker", "★", apply=True)
    assert r.json()["chapters_moved"] == 2
    db.expire_all()
    assert _placement(db, s) == [(0, None), (1, "★ 一日"), (2, "★ 一日"), (3, "★ 二日")]
