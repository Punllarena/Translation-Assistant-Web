import threading

from sqlalchemy import delete, inspect
from sqlalchemy.orm import Session

from api.accounts import AlreadySetUp, claim_first_admin
from api.models import User

PW = "pw-setup-123456"


def test_status_needs_setup_until_a_user_exists(app_client, make_user):
    assert app_client.get("/setup/status").json() == {"needs_setup": True}
    make_user()
    assert app_client.get("/setup/status").json() == {"needs_setup": False}


def test_claim_creates_an_admin_and_signs_in(app_client):
    r = app_client.post("/setup/admin", json={"email": " Root@Example.com ", "username": "root",
                                              "password": PW})
    assert r.status_code == 201
    assert r.json()["email"] == "root@example.com" and r.json()["is_admin"] is True
    assert app_client.get("/auth/me").json()["email"] == "root@example.com"
    assert app_client.get("/setup/status").json() == {"needs_setup": False}


def test_claim_creates_no_profile(app_client, db):
    r = app_client.post("/setup/admin", json={"email": "root@example.com", "username": "root",
                                              "password": PW})
    assert r.status_code == 201
    assert inspect(db.connection()).has_table("profiles") is False


def test_claim_after_setup_is_409_with_a_sign_in_hint(app_client, make_user):
    make_user()
    r = app_client.post("/setup/admin", json={"email": "late@example.com", "username": "root",
                                              "password": PW})
    assert r.status_code == 409
    assert r.json()["detail"] == "Setup is already complete; sign in instead."


def test_short_password_is_422(app_client):
    r = app_client.post("/setup/admin", json={"email": "a@example.com", "username": "root",
                                              "password": "short"})
    assert r.status_code == 422


def test_two_concurrent_claims_create_exactly_one_admin(engine):
    a, b = Session(engine), Session(engine)
    outcome = {}
    try:
        claim_first_admin(a, "a@example.com", PW, "aa_admin")  # holds the lock, not committed yet

        def second():
            try:
                claim_first_admin(b, "b@example.com", PW, "bb_admin")
                outcome["b"] = "created"
            except AlreadySetUp:
                outcome["b"] = "refused"
            finally:
                b.rollback()

        t = threading.Thread(target=second)
        t.start()
        t.join(0.5)
        assert t.is_alive(), "the second claim must wait for the first one's lock"
        a.commit()
        t.join(5)
        assert outcome == {"b": "refused"}
    finally:
        a.rollback()
        emails = ["a@example.com", "b@example.com"]
        ids = [u.id for u in a.query(User).filter(User.email.in_(emails))]
        a.execute(delete(User).where(User.id.in_(ids)))
        a.commit()
        a.close()
        b.close()
