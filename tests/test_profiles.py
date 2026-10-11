from datetime import UTC, datetime, timedelta

import pytest


def test_profiles_require_authentication(app_client):
    assert app_client.get("/profiles").status_code == 401


def test_list_returns_only_my_profiles(app_client, db, make_user, login):
    from api.models import Profile

    mine = make_user(email="mine@example.com")
    theirs = make_user(email="theirs@example.com")
    db.add_all([
        Profile(user_id=mine.id, name="default", is_default=True),
        Profile(user_id=theirs.id, name="default", is_default=True),
        Profile(user_id=theirs.id, name="secret"),
    ])
    db.flush()
    login(app_client, "mine@example.com")
    names = [p["name"] for p in app_client.get("/profiles").json()]
    assert names == ["default"]


def test_create_profile(app_client, make_user, login):
    make_user(email="c@example.com")
    login(app_client, "c@example.com")
    r = app_client.post("/profiles", json={"name": "wn", "parse_chars": "。！"})
    assert r.status_code == 201
    assert r.json()["parse_chars"] == "。！"


def test_duplicate_profile_name_is_409(app_client, make_user, login):
    make_user(email="d@example.com")
    login(app_client, "d@example.com")
    app_client.post("/profiles", json={"name": "wn"})
    assert app_client.post("/profiles", json={"name": "wn"}).status_code == 409


def test_duplicate_409_keeps_earlier_writes_of_the_request(app_client, db, make_user, login):
    from sqlalchemy import select

    from api.models import Session as SessionRow

    make_user(email="d2@example.com")
    login(app_client, "d2@example.com")
    app_client.post("/profiles", json={"name": "wn"})
    row = db.scalar(select(SessionRow))
    before = datetime.now(UTC) - timedelta(minutes=5)  # stale, so the request refreshes it
    row.last_seen_at = before
    db.flush()
    assert app_client.post("/profiles", json={"name": "wn"}).status_code == 409
    db.refresh(row)
    assert row.last_seen_at > before
    assert app_client.post("/profiles", json={"name": "other"}).status_code == 201
    assert len(app_client.get("/profiles").json()) == 2


def test_patch_to_duplicate_name_is_409(app_client, make_user, login):
    make_user(email="d3@example.com")
    login(app_client, "d3@example.com")
    app_client.post("/profiles", json={"name": "a"})
    pid = app_client.post("/profiles", json={"name": "b"}).json()["id"]
    assert app_client.patch(f"/profiles/{pid}", json={"name": "a"}).status_code == 409


def test_same_profile_name_is_allowed_for_two_users(app_client, db, make_user, login):
    make_user(email="e1@example.com")
    make_user(email="e2@example.com")
    login(app_client, "e1@example.com")
    assert app_client.post("/profiles", json={"name": "shared"}).status_code == 201
    app_client.post("/auth/logout")
    login(app_client, "e2@example.com")
    assert app_client.post("/profiles", json={"name": "shared"}).status_code == 201


def test_patch_updates_parse_chars(app_client, make_user, login):
    make_user(email="f@example.com")
    login(app_client, "f@example.com")
    pid = app_client.post("/profiles", json={"name": "wn"}).json()["id"]
    r = app_client.patch(f"/profiles/{pid}", json={"parse_chars": "。"})
    assert r.status_code == 200 and r.json()["parse_chars"] == "。"


def test_delete_last_profile_is_409(app_client, make_user, login):
    make_user(email="g@example.com")
    login(app_client, "g@example.com")
    pid = app_client.post("/profiles", json={"name": "only"}).json()["id"]
    assert app_client.delete(f"/profiles/{pid}").status_code == 409


def test_delete_one_of_several(app_client, make_user, login):
    make_user(email="h@example.com")
    login(app_client, "h@example.com")
    app_client.post("/profiles", json={"name": "keep"})
    pid = app_client.post("/profiles", json={"name": "drop"}).json()["id"]
    assert app_client.delete(f"/profiles/{pid}").status_code == 204
    assert [p["name"] for p in app_client.get("/profiles").json()] == ["keep"]


@pytest.mark.parametrize("field", ["name", "parse_chars", "is_default"])
def test_patch_explicit_null_is_422(app_client, make_user, login, field):
    make_user(email="n@example.com")
    login(app_client, "n@example.com")
    pid = app_client.post("/profiles", json={"name": "wn"}).json()["id"]
    assert app_client.patch(f"/profiles/{pid}", json={field: None}).status_code == 422
