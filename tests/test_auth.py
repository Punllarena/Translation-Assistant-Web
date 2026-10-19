from datetime import UTC, datetime, timedelta

import pytest

from api.models import Session as SessionRow
from api.security import account_limiter, address_limiter, email_limiter


def test_login_sets_cookie_and_returns_user(app_client, make_user):
    make_user(email="a@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"login": "a@example.com", "password": "pw-correct"})
    assert r.status_code == 200
    assert r.json()["email"] == "a@example.com"
    assert "ta_session" in r.cookies


def test_login_rejects_wrong_password(app_client, make_user):
    make_user(email="b@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"login": "b@example.com", "password": "nope"})
    assert r.status_code == 401
    assert "ta_session" not in r.cookies


def test_login_rejects_unknown_email_with_identical_response(app_client, make_user):
    make_user(email="known@example.com", password="pw-correct")
    def attempt(email: str):
        return app_client.post("/auth/login", json={"login": email, "password": "nope"})

    wrong = attempt("known@example.com")
    unknown = attempt("ghost@example.com")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()
    assert "ta_session" not in unknown.cookies


def test_me_requires_a_session(app_client):
    assert app_client.get("/auth/me").status_code == 401


def test_me_returns_the_logged_in_user(app_client, make_user):
    make_user(email="c@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"login": "c@example.com", "password": "pw-correct"})
    r = app_client.get("/auth/me")
    assert r.status_code == 200 and r.json()["email"] == "c@example.com"


def test_malformed_cookie_is_401_not_500(app_client):
    app_client.cookies.set("ta_session", "not-a-real-token")
    r = app_client.get("/auth/me")
    assert r.status_code == 401


def test_expired_session_is_401(app_client, db, make_user):
    user = make_user(email="d@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"login": "d@example.com", "password": "pw-correct"})
    row = db.query(SessionRow).filter_by(user_id=user.id).one()
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert app_client.get("/auth/me").status_code == 401


def test_logout_deletes_the_session(app_client, db, make_user):
    user = make_user(email="e@example.com", password="pw-correct")
    app_client.post("/auth/login", json={"login": "e@example.com", "password": "pw-correct"})
    assert app_client.post("/auth/logout").status_code == 204
    assert db.query(SessionRow).filter_by(user_id=user.id).count() == 0
    assert app_client.get("/auth/me").status_code == 401


def test_login_cookie_flags(app_client, make_user):
    make_user(email="g@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"login": "g@example.com", "password": "pw-correct"})
    cookie = r.headers["set-cookie"]
    assert cookie.startswith("ta_session=")
    assert "httponly" in cookie.lower()
    assert "samesite=lax" in cookie.lower()


@pytest.mark.parametrize("secure", [True, False])
def test_cookie_secure_flag_tracks_setting(app_client, make_user, monkeypatch, secure):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "cookie_secure", secure)
    make_user(email="h@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"login": "h@example.com", "password": "pw-correct"})
    assert ("secure" in r.headers["set-cookie"].lower().split("; ")) is secure


def test_repeated_failures_are_rate_limited(app_client, make_user):
    make_user(email="f@example.com", password="pw-correct")
    cap = address_limiter.max_attempts
    bad = {"login": "f@example.com", "password": "bad"}
    codes = [app_client.post("/auth/login", json=bad).status_code for _ in range(cap + 1)]
    assert codes == [401] * cap + [429]
    good = {"login": "f@example.com", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429


def test_account_bucket_limits_across_addresses(app_client, make_user):
    make_user(email="f@example.com", password="pw-correct")
    for _ in range(email_limiter.max_attempts):
        email_limiter.record_failure("f@example.com")
    good = {"login": " F@Example.com ", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429
    other = {"login": "other@example.com", "password": "x"}
    assert app_client.post("/auth/login", json=other).status_code == 401


def test_flooding_email_keys_cannot_evict_address_bucket(
    app_client, make_user, monkeypatch
):
    from api import security

    make_user(email="f@example.com", password="pw-correct")
    for _ in range(address_limiter.max_attempts):
        address_limiter.record_failure("testclient")
    monkeypatch.setattr(security, "MAX_TRACKED_KEYS", 3)
    for i in range(10):  # well past the cap, so email entries are evicted
        email_limiter.record_failure(f"flood{i}@example.com")
    assert len(email_limiter._failures) == 3
    good = {"login": "f@example.com", "password": "pw-correct"}
    assert app_client.post("/auth/login", json=good).status_code == 429


def test_login_email_lookup_is_case_and_whitespace_insensitive(app_client, make_user):
    make_user(email="me@example.com", password="pw-correct")
    r = app_client.post("/auth/login", json={"login": " Me@Example.com ", "password": "pw-correct"})
    assert r.status_code == 200


def test_login_by_username_ignores_case(app_client, make_user):
    make_user(email="named@example.com", password="pw-correct")  # username "named"
    r = app_client.post("/auth/login", json={"login": " NAMED ", "password": "pw-correct"})
    assert r.status_code == 200 and r.json()["username"] == "named"


def test_username_bucket_behaves_the_same_whether_or_not_the_account_exists(
    app_client, make_user
):
    make_user(email="both@example.com", password="pw-correct")
    for login in ("both", "nobody"):
        for _ in range(email_limiter.max_attempts):
            app_client.post("/auth/login", json={"login": login, "password": "bad"})
            address_limiter.reset("testclient")  # isolate the account bucket
        r = app_client.post("/auth/login", json={"login": login, "password": "bad"})
        assert r.status_code == 429


def test_an_exhausted_account_fails_like_a_wrong_password_from_either_login(
    app_client, make_user
):
    make_user(email="capped@example.com", password="pw-correct")
    for i in range(account_limiter.max_attempts):
        login = "capped@example.com" if i % 2 else "capped"
        r = app_client.post("/auth/login", json={"login": login, "password": "bad"})
        assert r.status_code == 401
        address_limiter.reset("testclient")
    # Neither login-string bucket is full, so no 429; the right password still gets the same 401.
    for login in ("capped", "capped@example.com"):
        r = app_client.post("/auth/login", json={"login": login, "password": "pw-correct"})
        assert r.status_code == 401 and r.json()["detail"] == "invalid credentials"


def test_a_successful_login_clears_the_account_counter(app_client, make_user):
    user = make_user(email="clear@example.com", password="pw-correct")
    for _ in range(account_limiter.max_attempts - 1):
        account_limiter.record_failure(f"user:{user.id}")
    r = app_client.post("/auth/login", json={"login": "clear", "password": "pw-correct"})
    assert r.status_code == 200
    assert account_limiter.check(f"user:{user.id}")


def test_concurrent_logins_get_no_more_guesses_than_the_cap(monkeypatch):
    """Call the handler from many threads at once with a slow verify: before the limiters
    charged up front, every request passed the check before any failure was recorded."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor
    from types import SimpleNamespace

    from fastapi import HTTPException, Response

    from api.routers import auth
    from api.schemas.auth import LoginRequest

    verifies = []
    lock = threading.Lock()

    def slow_verify(password, hashed):
        time.sleep(0.05)
        with lock:
            verifies.append(password)
        return False

    monkeypatch.setattr(auth, "verify_password", slow_verify)
    monkeypatch.setattr(auth, "find_by_username", lambda db, name: None)  # no DB from threads

    def attempt(i):
        request = SimpleNamespace(client=SimpleNamespace(host=f"10.0.0.{i}"))  # many addresses
        try:
            auth.login(LoginRequest(login="victim", password="guess"), request, Response(), None)
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=40) as pool:
        codes = list(pool.map(attempt, range(40)))
    cap = email_limiter.max_attempts
    assert len(verifies) == cap
    assert codes.count(401) == cap and codes.count(429) == 40 - cap


def test_a_full_account_bucket_takes_no_further_charge(app_client, make_user):
    user = make_user(email="full@example.com", password="pw-correct")
    key = f"user:{user.id}"
    for _ in range(account_limiter.max_attempts):
        account_limiter.record_failure(key)
    before = list(account_limiter._failures[key])
    r = app_client.post("/auth/login", json={"login": "full", "password": "pw-correct"})
    assert r.status_code == 401
    assert list(account_limiter._failures[key]) == before
