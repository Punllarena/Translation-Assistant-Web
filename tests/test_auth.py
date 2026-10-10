from datetime import UTC, datetime, timedelta

import pytest

from api.models import Session as SessionRow


def test_login_sets_cookie_and_returns_user(app_client, make_user):
    make_user(email="a@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"email": "a@example.com", "password": "pw-correct"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"
    assert "ta_session" in r.cookies


def test_login_rejects_wrong_password(app_client, make_user):
    make_user(email="b@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"email": "b@example.com", "password": "nope"})
    assert r.status_code == 401
    assert "ta_session" not in r.cookies


def test_login_rejects_unknown_email_with_identical_response(app_client, make_user):
    make_user(email="known@example.com", password="pw-correct")
    wrong = app_client.post("/auth/login", json={"email": "known@example.com", "password": "nope"})
    unknown = app_client.post("/auth/login", json={"email": "ghost@example.com", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "ta_session" not in unknown.cookies


def test_me_requires_a_session(app_client):
    assert app_client.get("/auth/me").status_code == 401


def test_me_returns_the_logged_in_user(app_client, make_user):
    make_user(email="c@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"email": "c@example.com", "password": "pw-correct"})
    r = app_client.get("/auth/me")
    assert r.status_code == 200 and r.json()["email"] == "c@example.com"


def test_malformed_cookie_is_401_not_500(app_client):
    app_client.cookies.set("ta_session", "not-a-real-token")
    r = app_client.get("/auth/me")
    assert r.status_code == 401


def test_expired_session_is_401(app_client, db, make_user):
    user = make_user(email="d@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"email": "d@example.com", "password": "pw-correct"})
    row = db.query(SessionRow).filter_by(user_id=user.id).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert app_client.get("/auth/me").status_code == 401


def test_logout_deletes_the_session(app_client, db, make_user):
    user = make_user(email="e@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"email": "e@example.com", "password": "pw-correct"})
    assert app_client.post("/auth/logout").status_code == 204
    assert db.query(SessionRow).filter_by(user_id=user.id).count() == 0
    assert app_client.get("/auth/me").status_code == 401


def test_login_cookie_flags(app_client, make_user):
    make_user(email="g@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"email": "g@example.com", "password": "pw-correct"})
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("ta_session=")
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()


@pytest.mark.parametrize("secure", [True, False])
def test_cookie_secure_flag_tracks_setting(app_client, make_user, monkeypatch, secure):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "cookie_secure", secure)
    make_user(email="h@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"email": "h@example.com", "password": "pw-correct"})
    assert ("secure" in r.headers["set-cookie"].lower().split("; ")) is secure


@pytest.fixture
def clean_limiter():
    from api.security import address_limiter, email_limiter

    def clear():
        address_limiter.reset("testclient")
        for k in ("f@example.com", "other@example.com"):
            email_limiter.reset(k)

    clear()
    try:
        yield address_limiter, email_limiter
    finally:
        clear()


def test_repeated_failures_are_rate_limited(app_client, make_user, clean_limiter):
    make_user(email="f@example.com", password="pw-correct")
    cap = clean_limiter[0].max_attempts
    bad = {"email": "f@example.com", "password": "bad"}
    codes = [app_client.post("/auth/login", json=bad).status_code for _ in range(cap + 1)]
    assert codes == [401] * cap + [429]
    good = {"email": "f@example.com", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429


def test_account_bucket_limits_across_addresses(app_client, make_user, clean_limiter):
    _, email_limiter = clean_limiter
    make_user(email="f@example.com", password="pw-correct")
    for _ in range(email_limiter.max_attempts):
        email_limiter.record_failure("f@example.com")
    good = {"email": " F@Example.com ", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429
    other = {"email": "other@example.com", "password": "x"}
    assert app_client.post("/auth/login", json=other).status_code == 401


def test_flooding_email_keys_cannot_evict_address_bucket(
    app_client, make_user, clean_limiter, monkeypatch
):
    from api import security

    address_limiter, email_limiter = clean_limiter
    make_user(email="f@example.com", password="pw-correct")
    for _ in range(address_limiter.max_attempts):
        address_limiter.record_failure("testclient")
    monkeypatch.setattr(security, "MAX_TRACKED_KEYS", 3)
    for i in range(10):  # well past the cap, so email entries are evicted
        email_limiter.record_failure(f"flood{i}@example.com")
    assert len(email_limiter._failures) == 3
    good = {"email": "f@example.com", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429


def test_login_email_lookup_is_case_and_whitespace_insensitive(app_client, make_user):
    make_user(email="me@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"email": " Me@Example.com ", "password": "pw-correct"})
    assert r.status_code == 200
