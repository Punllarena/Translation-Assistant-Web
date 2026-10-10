import os
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

os.environ.setdefault("TA_SECRET_KEY", "test-secret-key-at-least-32-chars-long")
os.environ.setdefault(
    "TA_DATABASE_URL", "postgresql+psycopg://ta:ta@localhost:5432/ta_test"
)
os.environ.setdefault("TA_COOKIE_SECURE", "false")


@pytest.fixture(scope="session")
def engine():
    """Create the test database once per session and migrate it to head."""
    admin_url = os.environ["TA_DATABASE_URL"].rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    name = os.environ["TA_DATABASE_URL"].rsplit("/", 1)[1]
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    eng = create_engine(os.environ["TA_DATABASE_URL"], future=True)
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
