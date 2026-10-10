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
