import pytest

from api.models import Document, Profile, Volume


def test_series_require_authentication(app_client):
    assert app_client.get("/series").status_code == 401


def test_create_and_list_only_mine(app_client, me, make_user, make_series):
    make_series(make_user(email="other@example.com"), "Theirs")
    r = app_client.post("/series", json={"title": "  Mine  "})
    assert r.status_code == 201
    assert r.json()["title"] == "Mine"
    assert [s["title"] for s in app_client.get("/series").json()] == ["Mine"]


def test_blank_title_is_422(app_client, me):
    assert app_client.post("/series", json={"title": "   "}).status_code == 422


def test_duplicate_title_is_409(app_client, me):
    app_client.post("/series", json={"title": "S"})
    assert app_client.post("/series", json={"title": "S"}).status_code == 409


def test_foreign_profile_reads_exactly_like_a_missing_one(app_client, db, me, make_user):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="p")
    db.add(theirs)
    db.flush()
    foreign = app_client.post("/series", json={"title": "S", "profile_id": theirs.id})
    missing = app_client.post("/series", json={"title": "S", "profile_id": 999999})
    assert foreign.status_code == missing.status_code == 422
    assert foreign.json() == missing.json()


def test_patch_renames_and_clears_profile(app_client, db, me):
    profile = Profile(user_id=me.id, name="p")
    db.add(profile)
    db.flush()
    sid = app_client.post("/series", json={"title": "S", "profile_id": profile.id}).json()["id"]
    r = app_client.patch(f"/series/{sid}", json={"title": "S2", "profile_id": None})
    assert r.status_code == 200
    assert (r.json()["title"], r.json()["profile_id"]) == ("S2", None)


def test_patch_foreign_profile_is_422(app_client, db, me, make_user, make_series):
    theirs = Profile(user_id=make_user(email="other@example.com").id, name="p")
    db.add(theirs)
    db.flush()
    series = make_series(me)
    r = app_client.patch(f"/series/{series.id}", json={"profile_id": theirs.id})
    assert r.status_code == 422


def test_patch_null_title_is_422(app_client, me, make_series):
    series = make_series(me)
    assert app_client.patch(f"/series/{series.id}", json={"title": None}).status_code == 422


def test_rename_onto_existing_title_is_409(app_client, me, make_series):
    make_series(me, "A")
    b = make_series(me, "B")
    assert app_client.patch(f"/series/{b.id}", json={"title": "A"}).status_code == 409


def test_delete_removes_the_chapters_and_volumes(app_client, db, me, make_series, make_doc):
    series = make_series(me)
    volume = Volume(series_id=series.id, subtitle="V1")
    db.add(volume)
    db.flush()
    doc = make_doc(me, ["a"], series=series, order=1, volume=volume)
    doc_id, volume_id = doc.id, volume.id
    assert app_client.delete(f"/series/{series.id}").status_code == 204
    db.expire_all()
    assert db.get(Document, doc_id) is None
    assert db.get(Volume, volume_id) is None


@pytest.mark.parametrize(
    ("method", "kwargs"), [("get", {}), ("patch", {"json": {"title": "x"}}), ("delete", {})]
)
def test_another_users_series_is_404(app_client, me, make_user, make_series, method, kwargs):
    theirs = make_series(make_user(email="other@example.com"), "Theirs")
    assert getattr(app_client, method)(f"/series/{theirs.id}", **kwargs).status_code == 404


def test_reorder_sets_the_given_order(app_client, me, make_series, make_doc):
    s = make_series(me)
    a, b, c = (make_doc(me, series=s, order=i, title=t) for i, t in [(1, "A"), (2, "B"), (3, "C")])
    r = app_client.put(f"/series/{s.id}/order", json={"document_ids": [c.id, a.id, b.id]})
    assert [(d["title"], d["series_order"]) for d in r.json()] == [("C", 1), ("A", 2), ("B", 3)]


@pytest.mark.parametrize("case", ["missing_one", "duplicate", "foreign"])
def test_reorder_needs_exactly_the_series_chapters(
    app_client, db, me, make_user, make_series, make_doc, case
):
    s = make_series(me)
    a, b = make_doc(me, series=s, order=1), make_doc(me, series=s, order=2)
    stranger = make_doc(make_user(email="other@example.com"), ["x"])
    ids = {
        "missing_one": [b.id],
        "duplicate": [a.id, a.id, b.id],
        "foreign": [b.id, a.id, stranger.id],
    }[case]
    assert app_client.put(f"/series/{s.id}/order", json={"document_ids": ids}).status_code == 422
    db.expire_all()
    assert (db.get(Document, a.id).series_order, db.get(Document, b.id).series_order) == (1, 2)


def test_renumber_sorts_titles_naturally(app_client, me, make_series, make_doc):
    s = make_series(me)
    for order, title in enumerate(["Ch 10", "Ch 2", "Ch 1"], start=1):
        make_doc(me, series=s, order=order, title=title)
    r = app_client.post(f"/series/{s.id}/renumber")
    assert [(d["chapter_title"], d["series_order"]) for d in r.json()] == [
        ("Ch 1", 1), ("Ch 2", 2), ("Ch 10", 3),
    ]


def test_renumber_falls_back_to_title(app_client, db, me, make_series, make_doc):
    s = make_series(me)
    make_doc(me, series=s, order=1, title="B")
    untitled = make_doc(me, series=s, order=2, title="A")
    untitled.chapter_title = ""
    db.flush()
    r = app_client.post(f"/series/{s.id}/renumber")
    assert [d["title"] for d in r.json()] == ["A", "B"]


@pytest.mark.parametrize(
    ("method", "suffix", "kwargs"),
    [("put", "/order", {"json": {"document_ids": [1]}}), ("post", "/renumber", {})],
)
def test_another_users_series_order_is_404(
    app_client, me, make_user, make_series, method, suffix, kwargs
):
    theirs = make_series(make_user(email="other@example.com"), "Theirs")
    r = getattr(app_client, method)(f"/series/{theirs.id}{suffix}", **kwargs)
    assert r.status_code == 404


def test_series_out_reports_the_heading_setting(app_client, me, make_series):
    s = make_series(me, "S")
    body = app_client.get(f"/series/{s.id}").json()
    assert body["syosetu_volume_mode"] == "all" and body["syosetu_volume_marker"] == ""


def test_patch_series_cannot_set_the_heading_setting(app_client, me, make_series, db):
    s = make_series(me, "S")
    app_client.patch(f"/series/{s.id}", json={"syosetu_volume_mode": "off"})
    db.refresh(s)
    assert s.syosetu_volume_mode == "all"


def test_changing_the_syosetu_url_forgets_the_old_headings(app_client, me, make_series, db):
    s = make_series(me, "S")
    s.syosetu_url = "https://ncode.syosetu.com/n1/"
    s.syosetu_headings, s.syosetu_volume_mode, s.syosetu_volume_marker = [[1, "★ a"]], "marker", "★"
    db.flush()
    app_client.patch(f"/series/{s.id}", json={"syosetu_url": "https://ncode.syosetu.com/n1/"})
    db.refresh(s)
    assert s.syosetu_headings == [[1, "★ a"]] and s.syosetu_volume_mode == "marker"
    app_client.patch(f"/series/{s.id}", json={"syosetu_url": "https://ncode.syosetu.com/n2/"})
    db.refresh(s)
    assert (s.syosetu_headings, s.syosetu_volume_mode, s.syosetu_volume_marker) == (None, "all", "")


def test_template_round_trip(app_client, me, make_series):
    s = make_series(me, "S")
    r = app_client.post(f"/series/{s.id}/volumes", json={"volume_index": "2"})
    assert r.status_code == 201
    r = app_client.patch(f"/series/{s.id}", json={"volume_title_template": "{series} Vol. {index}"})
    assert r.status_code == 200
    assert r.json()["volume_title_template"] == "{series} Vol. {index}"
    assert r.json()["volume_title_template_effective"] == "{series} Vol. {index}"
    vols = app_client.get(f"/series/{s.id}/volumes").json()
    assert vols[0]["full_title"] == "S Vol. 2"


def test_template_rejects_unknown_placeholder(app_client, me, make_series):
    s = make_series(me, "S")
    r = app_client.patch(f"/series/{s.id}", json={"volume_title_template": "{Series}"})
    assert r.status_code == 422
    assert "Series" in r.text


def test_template_rejects_overlong(app_client, me, make_series):
    s = make_series(me, "S")
    r = app_client.patch(f"/series/{s.id}", json={"volume_title_template": "x" * 301})
    assert r.status_code == 422


def test_template_null_is_422(app_client, me, make_series):
    s = make_series(me, "S")
    r = app_client.patch(f"/series/{s.id}", json={"volume_title_template": None})
    assert r.status_code == 422


def test_template_blank_means_default(app_client, me, make_series):
    from api.core.volume_names import DEFAULT_TEMPLATE

    s = make_series(me, "S")
    app_client.patch(f"/series/{s.id}", json={"volume_title_template": "{series} Vol. {index}"})
    r = app_client.patch(f"/series/{s.id}", json={"volume_title_template": ""})
    assert r.status_code == 200
    assert r.json()["volume_title_template"] == ""
    assert r.json()["volume_title_template_effective"] == DEFAULT_TEMPLATE
