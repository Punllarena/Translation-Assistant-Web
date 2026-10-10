import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

os.environ.setdefault("TA_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
os.environ.setdefault(
    "TA_DATABASE_URL", "postgresql+psycopg://ta:ta@localhost:5432/ta_test"
)


@pytest.fixture
def insecure_cookies(monkeypatch):
    """TestClient speaks plain http, so a Secure cookie would never be stored.
    Scoped to the clients that need it: setting it for the whole suite would leak
    into tests that assert on the real default (see tests/test_config.py)."""
    from api.config import get_settings

    monkeypatch.setenv("TA_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(scope="session")
def engine():
    """Create the test database once per session and migrate it to head."""
    url = make_url(os.environ["TA_DATABASE_URL"])
    name = url.database
    if not name or not name.endswith("_test"):
        pytest.exit(
            "refusing to run: TA_DATABASE_URL must name a database ending in "
            f"_test, got {name!r}",
            returncode=2,
        )
    admin = create_engine(
        url.set(database="postgres"), isolation_level="AUTOCOMMIT", future=True
    )
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        cwd=Path(__file__).resolve().parent.parent,
    )
    eng = create_engine(url, future=True)
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine):
    """One test, one transaction, always rolled back."""
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def app_client(db, insecure_cookies):
    from api.deps import db_session
    from api.main import create_app

    app = create_app()
    app.dependency_overrides[db_session] = lambda: db
    with TestClient(app) as client:
        yield client


@pytest.fixture
def make_user(db):
    from api.models import User
    from api.security import hash_password

    def _make(
        email: str = "user@example.com", password: str = "pw-correct", is_admin: bool = False
    ):
        user = User(email=email, password_hash=hash_password(password), is_admin=is_admin)
        db.add(user)
        db.flush()
        return user

    return _make


@pytest.fixture(autouse=True)
def _reset_login_limiters():
    """Login limiters are process-global; clear them around every test."""
    from api.security import address_limiter, email_limiter

    def clear():
        for limiter in (address_limiter, email_limiter):
            with limiter._lock:
                limiter._failures.clear()

    clear()
    yield
    clear()


@pytest.fixture
def login():
    """Return login(client, email, password) -> response."""

    def _login(client, email, password="pw-correct"):
        return client.post("/auth/login", json={"email": email, "password": password})

    return _login


@pytest.fixture
def other_users_profile_id(app_client, make_user, login):
    """An owner's profile id, with the client logged in as a different user."""
    make_user(email="owner@example.com")
    make_user(email="intruder@example.com")
    login(app_client, "owner@example.com")
    pid = app_client.post("/profiles", json={"name": "owned"}).json()["id"]
    app_client.post("/auth/logout")
    login(app_client, "intruder@example.com")
    return pid


@pytest.fixture
def me(app_client, make_user, login):
    """A signed-in user: the client carries their session."""
    user = make_user(email="me@example.com")
    login(app_client, "me@example.com")
    return user


@pytest.fixture
def make_series(db):
    from api.models import Series

    def _make(user, title="S"):
        series = Series(user_id=user.id, title=title)
        db.add(series)
        db.flush()
        return series

    return _make


@pytest.fixture
def make_doc(db):
    """make_doc(user, raws, ...) -> Document whose lines are `raws`, all '%'-prefixed.

    With translated=True each line's translation is 'tr:<raw>'; otherwise empty.
    chapter_title is set to `title`, as the desktop does for chapters."""
    from api.models import Document, Line

    def _make(user, raws=(), *, series=None, order=0, title="Ch", volume=None, translated=True):
        doc = Document(
            user_id=user.id,
            title=title,
            chapter_title=title,
            series_id=series.id if series else None,
            volume_id=volume.id if volume else None,
            series_order=order,
        )
        db.add(doc)
        db.flush()
        db.add_all(
            Line(
                document_id=doc.id,
                line_number=i,
                prefix="%",
                raw_text=raw,
                translated_text=f"tr:{raw}" if translated else "",
            )
            for i, raw in enumerate(raws)
        )
        db.flush()
        return doc

    return _make
