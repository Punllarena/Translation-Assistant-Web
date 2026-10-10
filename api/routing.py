"""The request/commit boundary.

Committing in a ``yield`` dependency's exit path does not work: FastAPI runs it
*after* the response has been sent, so a commit that fails there (lost connection,
deadlock, serialization failure) cannot turn a 201 into a 500 — the client is told
the write succeeded while nothing was persisted. The route class below commits
after the endpoint returns but before the response is emitted, which keeps that
failure in the request path where FastAPI turns it into a 500.

Handlers therefore never commit; they ``flush()`` when they need constraint errors
or generated ids in-request, and ``db_session``'s teardown is rollback-and-close.
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.routing import APIRoute

# Where db_session parks the session for this request, so the route can commit it.
SESSION_STATE_ATTR = "ta_db_session"


class CommitOnResponseRoute(APIRoute):
    """Commits the request's session before the response leaves the handler."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handle = super().get_route_handler()

        async def commit_then_respond(request: Request) -> Response:
            response = await handle(request)
            session = getattr(request.state, SESSION_STATE_ATTR, None)
            if session is not None:
                # Raises into the request: FastAPI answers 5xx, teardown rolls back.
                session.commit()
            return response

        return commit_then_respond


def api_router(**kwargs: Any) -> APIRouter:
    """An APIRouter whose routes commit in the request path.

    Every router in this app must be built with this; `test_commit_boundary.py`
    fails the build if one is not. (An included router keeps its own route class,
    so setting it on the app alone would not reach them.)
    """
    kwargs.setdefault("route_class", CommitOnResponseRoute)
    return APIRouter(**kwargs)
