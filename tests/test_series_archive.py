import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text

_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def test_new_series_default_status_and_source(app_client, me):
    s = app_client.post("/series", json={"title": "A"}).json()
    assert (s["status"], s["source"], s["archived_at"], s["syosetu_updated_at"]) == (
        "ongoing", "other", None, None)


def test_a_series_created_with_a_syosetu_url_is_a_syosetu_source(app_client, me):
    s = app_client.post(
        "/series", json={"title": "B", "syosetu_url": "https://ncode.syosetu.com/n1/"}).json()
    assert s["source"] == "syosetu"


def test_archive_and_unarchive(app_client, me, make_series):
    s = make_series(me)
    first = app_client.post(f"/series/{s.id}/archive").json()["archived_at"]
    assert first is not None
    assert app_client.post(f"/series/{s.id}/archive").json()["archived_at"] == first
    assert app_client.post(f"/series/{s.id}/unarchive").json()["archived_at"] is None
    assert app_client.post(f"/series/{s.id}/unarchive").status_code == 200


def test_archived_series_still_listed_and_editable(app_client, me, make_series):
    s = make_series(me)
    app_client.post(f"/series/{s.id}/archive")
    assert [x["id"] for x in app_client.get("/series").json()] == [s.id]
    assert app_client.patch(
        f"/series/{s.id}", json={"status": "completed"}).json()["status"] == "completed"


def test_archive_another_users_series_is_404(app_client, me, make_user, make_series):
    other = make_series(make_user(email="other@example.com"), title="Theirs")
    assert app_client.post(f"/series/{other.id}/archive").status_code == 404
    assert app_client.post(f"/series/{other.id}/unarchive").status_code == 404


def test_patch_sets_status_and_source(app_client, me, make_series):
    s = make_series(me)
    r = app_client.patch(f"/series/{s.id}", json={"status": "on_hold", "source": "epub"}).json()
    assert (r["status"], r["source"]) == ("on_hold", "epub")


@pytest.mark.parametrize(
    "body", [{"status": "paused"}, {"source": "pdf"}, {"status": None}, {"source": None}])
def test_unknown_status_or_source_is_422(app_client, me, make_series, body):
    assert app_client.patch(f"/series/{make_series(me).id}", json=body).status_code == 422


def test_setting_a_syosetu_url_later_keeps_the_source(app_client, me, make_series):
    s = make_series(me)
    r = app_client.patch(
        f"/series/{s.id}", json={"syosetu_url": "https://ncode.syosetu.com/n1/"}).json()
    assert r["source"] == "other"


def test_migration_backfills_source_from_the_syosetu_url(db, make_user, make_series):
    (path,) = _VERSIONS.glob("*_series_archive_status_source.py")
    spec = importlib.util.spec_from_file_location("mig_series_archive", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    user = make_user()
    syo = make_series(user, title="Syo")
    make_series(user, title="Plain")
    syo.syosetu_url = "https://ncode.syosetu.com/n1/"
    db.flush()
    db.execute(text("UPDATE series SET source = 'other'"))  # as the new column starts
    db.execute(text(module.BACKFILL_SOURCE))
    rows = dict(db.execute(text(
        "SELECT title, source || '/' || status FROM series WHERE user_id = :u"),
        {"u": user.id}).all())
    assert rows == {"Syo": "syosetu/ongoing", "Plain": "other/ongoing"}
