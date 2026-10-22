import pytest
from sqlalchemy import inspect

from api.accounts import create_admin


def test_create_admin_makes_an_admin_and_no_profile(db):
    user = create_admin(db, "root@example.com", "pw-root-12345")
    assert user.is_admin is True
    assert user.password_hash.startswith("$argon2")
    assert inspect(db.connection()).has_table("profiles") is False


def test_create_admin_normalises_email(db):
    user = create_admin(db, " Root@Example.COM ", "pw-root-12345")
    assert user.email == "root@example.com"


def test_create_admin_refuses_a_duplicate_email(db):
    create_admin(db, "dup@example.com", "pw-dup-123456")
    with pytest.raises(ValueError, match="already exists"):
        create_admin(db, "DUP@example.com", "pw-dup-123456")


def test_create_admin_refuses_a_short_password(db):
    with pytest.raises(ValueError, match="at least 12"):
        create_admin(db, "short@example.com", "tiny")
