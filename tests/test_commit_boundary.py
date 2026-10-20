"""The commit happens in the request path, so a failed commit is a 5xx.

See api/routing.py: committing in the dependency's exit path would run after the
response was already sent, telling the client 201 while nothing was persisted.
"""

import pytest
from fastapi import Request
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from api.main import create_app
from api.routing import SESSION_STATE_ATTR, CommitOnResponseRoute


def _api_routes(router) -> list[APIRoute]:
    """Every APIRoute reachable from an app, through included routers."""
    found: list[APIRoute] = []
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute):
            found.append(route)
        inner = getattr(route, "original_router", None)  # FastAPI's _IncludedRouter
        if inner is not None:
            found.extend(_api_routes(inner))
    return found


def test_every_route_commits_in_the_request_path():
    routes = _api_routes(create_app())
    assert routes
    offenders = [r.path for r in routes if not isinstance(r, CommitOnResponseRoute)]
    assert offenders == [], f"{offenders} must be built with api_router()"


class _CommitBoom:
    """Stands in for the request's session, at commit time only."""

    def __init__(self) -> None:
        self.calls = 0

    def commit(self) -> None:
        self.calls += 1
        raise OperationalError("COMMIT", {}, Exception("connection lost at commit"))


@pytest.fixture
def boom(db, insecure_cookies):
    """A client whose request-path commit can be armed to fail."""
    from api.deps import db_session

    failure = _CommitBoom()
    armed = {"on": False}

    def override(request: Request):
        if armed["on"]:
            setattr(request.state, SESSION_STATE_ATTR, failure)
        yield db

    app = create_app()
    app.dependency_overrides[db_session] = override
    # raise_server_exceptions=False: respond like a deployment would, not re-raise.
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, armed, failure


def test_a_failing_commit_is_a_5xx_not_a_201(boom, make_user, login):
    client, armed, failure = boom
    make_user(email="commit@example.com")
    assert login(client, "commit@example.com").status_code == 200

    assert client.post("/profiles", json={"name": "before"}).status_code == 201

    armed["on"] = True
    response = client.post("/profiles", json={"name": "after"})
    assert response.status_code >= 500, "a failed commit must not be reported as success"
    assert failure.calls == 1


def test_a_failing_commit_on_a_read_is_also_a_5xx(boom, make_user, login):
    client, armed, failure = boom
    make_user(email="read@example.com")
    login(client, "read@example.com")
    armed["on"] = True
    assert client.get("/profiles").status_code >= 500
    assert failure.calls == 1


def test_a_real_request_persists_although_no_handler_commits(
    engine, monkeypatch, insecure_cookies
):
    """End to end against a real session: the route class is what makes writes stick."""
    from sqlalchemy import delete, select
    from sqlalchemy.orm import Session, sessionmaker

    from api import deps
    from api.models import User
    from api.security import hash_password

    monkeypatch.setattr(
        deps, "SessionLocal", sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    )
    with Session(engine) as setup:
        setup.add(User(email="real@example.com", password_hash=hash_password("pw-correct")))
        setup.commit()
    try:
        with TestClient(create_app()) as client:
            login = client.post(
                "/auth/login", json={"login": "real@example.com", "password": "pw-correct"}
            )
            assert login.status_code == 200
            assert client.post("/profiles", json={"name": "persisted"}).status_code == 201
        # A fresh session: only committed rows are visible.
        with Session(engine) as check:
            user = check.scalar(select(User).where(User.email == "real@example.com"))
            assert [p.name for p in user.profiles] == ["persisted"]
    finally:
        with Session(engine) as cleanup:
            cleanup.execute(delete(User).where(User.email == "real@example.com"))
            cleanup.commit()


def test_commit_runs_off_the_event_loop(db, insecure_cookies, make_user, login):
    """A synchronous session.commit() in the route would block the loop that has to run
    a concurrent request's commit (row-lock deadlock)."""
    import asyncio

    from api.deps import db_session

    on_loop: list[bool] = []

    class Spy:
        def commit(self) -> None:
            try:
                asyncio.get_running_loop()
                on_loop.append(True)
            except RuntimeError:
                on_loop.append(False)
            db.commit()

    spy = Spy()

    def override(request: Request):
        setattr(request.state, SESSION_STATE_ATTR, spy)
        yield db

    app = create_app()
    app.dependency_overrides[db_session] = override
    make_user(email="loop@example.com")
    with TestClient(app) as client:
        login(client, "loop@example.com")
        on_loop.clear()
        assert client.post("/profiles", json={"name": "off-loop"}).status_code == 201
    assert on_loop == [False]
