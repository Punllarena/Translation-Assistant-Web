"""Shared translation of database errors into HTTP responses.

One helper, so every router answers a unique violation the same way (and nobody
re-derives the SQLSTATE constant).
"""

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

UNIQUE_VIOLATION = "23505"


def conflict(exc: IntegrityError, message: str) -> HTTPException:
    """409 for a unique violation; any other integrity error is re-raised (500).

    Returns the exception so callers read ``raise conflict(exc, "...") from exc``.
    """
    if getattr(exc.orig, "sqlstate", None) != UNIQUE_VIOLATION:
        raise exc
    return HTTPException(status.HTTP_409_CONFLICT, message)
