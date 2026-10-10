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


def test_delete_keeps_chapters_unsorted(app_client, db, me, make_series, make_doc):
    series = make_series(me)
    volume = Volume(series_id=series.id, title="V1")
    db.add(volume)
    db.flush()
    doc = make_doc(me, ["a"], series=series, order=1, volume=volume)
    assert app_client.delete(f"/series/{series.id}").status_code == 204
    db.expire_all()
    kept = db.get(Document, doc.id)
    assert kept is not None
    assert (kept.series_id, kept.volume_id) == (None, None)


@pytest.mark.parametrize(
    ("method", "kwargs"), [("get", {}), ("patch", {"json": {"title": "x"}}), ("delete", {})]
)
def test_another_users_series_is_404(app_client, me, make_user, make_series, method, kwargs):
    theirs = make_series(make_user(email="other@example.com"), "Theirs")
    assert getattr(app_client, method)(f"/series/{theirs.id}", **kwargs).status_code == 404
