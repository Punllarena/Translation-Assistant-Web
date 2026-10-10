import pytest
from datetime import datetime, timedelta, timezone

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
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
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
    from api.security import login_limiter

    def clear():
        for k in ("ip:testclient", "email:f@example.com", "email:other@example.com"):
            login_limiter.reset(k)

    clear()
    try:
        yield login_limiter
    finally:
        clear()


def test_repeated_failures_are_rate_limited(app_client, make_user, clean_limiter):
    make_user(email="f@example.com", password="pw-correct")
    cap = clean_limiter.max_attempts
    bad = {"email": "f@example.com", "password": "bad"}
    codes = [app_client.post("/auth/login", json=bad).status_code for _ in range(cap + 1)]
    assert codes == [401] * cap + [429]
    good = {"email": "f@example.com", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429


def test_account_bucket_limits_across_addresses(app_client, make_user, clean_limiter):
    make_user(email="f@example.com", password="pw-correct")
    cap = clean_limiter.max_attempts
    # Failures from other addresses exhaust only the (case-insensitive) email bucket.
    for _ in range(cap):
        clean_limiter.record_failure("email:f@example.com")
    good = {"email": " F@Example.com ", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429
    other = {"email": "other@example.com", "password": "x"}
    assert app_client.post("/auth/login", json=other).status_code == 401
