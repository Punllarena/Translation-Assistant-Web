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
os.environ.setdefault("TA_COOKIE_SECURE", "false")


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
def app_client(db):
    from api.deps import db_session
    from api.main import create_app

    app = create_app()
    app.dependency_overrides[db_session] = lambda: db
    with TestClient(app) as client:
        yield client
