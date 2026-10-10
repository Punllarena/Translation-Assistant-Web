import pytest
from fastapi import HTTPException
from psycopg.errors import ForeignKeyViolation, UniqueViolation
from sqlalchemy.exc import IntegrityError

from api.errors import conflict


def _integrity_error(orig: Exception) -> IntegrityError:
    return IntegrityError("INSERT ...", {}, orig)


def test_a_unique_violation_becomes_a_409_with_the_callers_message():
    exc = conflict(_integrity_error(UniqueViolation("duplicate key")), "nope, taken")
    assert isinstance(exc, HTTPException)
    assert exc.status_code == 409 and exc.detail == "nope, taken"


def test_any_other_integrity_error_is_re_raised():
    """Not translated to 409: a foreign-key or not-null breach is a 500-worthy bug."""
    original = _integrity_error(ForeignKeyViolation("no such parent"))
    with pytest.raises(IntegrityError) as caught:
        conflict(original, "nope, taken")
    assert caught.value is original
