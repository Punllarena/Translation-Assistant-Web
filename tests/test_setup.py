import logging

from api.accounts import setup_token
from api.main import announce_setup
from api.models import Profile, User


def _body(**over):
    body = {"token": setup_token(), "email": "Root@Example.com", "password": "pw-root-123456"}
    return body | over


def test_setup_is_needed_only_without_users(app_client, make_user):
    assert app_client.get("/setup").json() == {"needed": True}
    make_user()
    assert app_client.get("/setup").json() == {"needed": False}


def test_setup_creates_an_admin_with_a_default_profile(app_client, db):
    r = app_client.post("/setup", json=_body())
    assert r.status_code == 201
    assert r.json()["email"] == "root@example.com"
    assert r.json()["is_admin"] is True
    user = db.query(User).one()
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["default"]
    assert app_client.get("/setup").json() == {"needed": False}


def test_setup_refuses_a_wrong_token(app_client, db):
    r = app_client.post("/setup", json=_body(token="nope"))
    assert r.status_code == 403
    assert db.query(User).count() == 0


def test_setup_refuses_once_an_account_exists(app_client, make_user):
    make_user()
    r = app_client.post("/setup", json=_body(email="other@example.com"))
    assert r.status_code == 409


def test_setup_refuses_a_short_password(app_client):
    assert app_client.post("/setup", json=_body(password="tiny")).status_code == 422


def test_setup_token_is_stable_and_not_the_secret():
    from api.config import get_settings

    assert setup_token() == setup_token()
    assert len(setup_token()) == 32
    assert setup_token() not in get_settings().secret_key


def test_announce_logs_the_link_when_no_users(caplog, monkeypatch, db):
    from api.config import get_settings

    monkeypatch.setenv("TA_COOKIE_SECURE", "true")  # the tools container sets it false
    monkeypatch.setenv("TA_SITE_ADDRESS", "localhost")
    get_settings.cache_clear()
    monkeypatch.setattr("api.main.SessionLocal", lambda: _NoClose(db))
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        announce_setup()
    assert f"https://localhost/setup?token={setup_token()}" in caplog.text


def test_announce_uses_http_when_cookies_are_insecure(caplog, monkeypatch, db, insecure_cookies):
    """The dev stack (Vite on :5173) speaks plain http and sets TA_COOKIE_SECURE=false."""
    monkeypatch.setenv("TA_SITE_ADDRESS", "localhost:5173")
    monkeypatch.setattr("api.main.SessionLocal", lambda: _NoClose(db))
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        announce_setup()
    assert f"http://localhost:5173/setup?token={setup_token()}" in caplog.text


def test_announce_is_silent_once_a_user_exists(caplog, monkeypatch, db, make_user):
    make_user()
    monkeypatch.setattr("api.main.SessionLocal", lambda: _NoClose(db))
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        announce_setup()
    assert "setup" not in caplog.text


class _NoClose:
    """Context manager over the test session that leaves it open (the db fixture owns it)."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, *exc):
        return False
