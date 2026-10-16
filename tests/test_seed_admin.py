import pytest

from api.accounts import create_admin
from api.models import Profile


def test_create_admin_makes_an_admin_with_a_default_profile(db):
    user = create_admin(db, "root@example.com", "pw-root-12345")
    assert user.is_admin is True
    assert user.password_hash.startswith("$argon2")
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["default"]


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
