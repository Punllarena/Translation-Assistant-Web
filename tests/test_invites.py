from datetime import UTC, datetime, timedelta

from api.models import Invite, Profile, User


def _login(client, email, password="pw-correct"):
    return client.post("/auth/login", json={"email": email, "password": password})


def test_non_admin_cannot_create_invites(app_client, make_user):
    make_user(email="plain@example.com")
    _login(app_client, "plain@example.com")
    assert app_client.post("/invites", json={}).status_code == 403


def test_non_admin_cannot_list_invites(app_client, make_user):
    make_user(email="plain2@example.com")
    _login(app_client, "plain2@example.com")
    assert app_client.get("/invites").status_code == 403


def test_anonymous_cannot_create_invites(app_client):
    assert app_client.post("/invites", json={}).status_code == 401


def test_admin_creates_an_invite_and_gets_the_token_once(app_client, db, make_user):
    make_user(email="admin@example.com", is_admin=True)
    _login(app_client, "admin@example.com")
    r = app_client.post("/invites", json={"email": "new@example.com"})
    assert r.status_code == 201
    token = r.json()["token"]
    assert token
    listed = app_client.get("/invites").json()
    assert len(listed) == 1
    assert "token" not in listed[0]  # plaintext is never retrievable again
    assert token not in str(listed)


def test_accept_invite_creates_user_with_default_profile(app_client, db, make_user):
    make_user(email="admin2@example.com", is_admin=True)
    _login(app_client, "admin2@example.com")
    token = app_client.post("/invites", json={}).json()["token"]
    app_client.post("/auth/logout")

    r = app_client.post(
        "/auth/accept-invite",
        json={"token": token, "email": "fresh@example.com", "password": "pw-fresh-123"},
    )
    assert r.status_code == 201
    assert _login(app_client, "fresh@example.com", "pw-fresh-123").status_code == 200
    user = db.query(User).filter_by(email="fresh@example.com").one()
    assert [p.name for p in db.query(Profile).filter_by(user_id=user.id)] == ["default"]


def test_accept_invite_normalises_email_so_user_can_log_in(app_client, make_user):
    make_user(email="admin5@example.com", is_admin=True)
    _login(app_client, "admin5@example.com")
    token = app_client.post("/invites", json={"email": "mixed@case.com"}).json()["token"]
    app_client.post("/auth/logout")
    r = app_client.post(
        "/auth/accept-invite",
        json={"token": token, "email": " Mixed@Case.COM ", "password": "pw-mixed-1234"},
    )
    assert r.status_code == 201
    assert r.json()["email"] == "mixed@case.com"
    assert _login(app_client, "mixed@case.com", "pw-mixed-1234").status_code == 200


def test_invite_bound_to_another_email_is_rejected(app_client, make_user):
    make_user(email="admin6@example.com", is_admin=True)
    _login(app_client, "admin6@example.com")
    token = app_client.post("/invites", json={"email": "a@example.com"}).json()["token"]
    app_client.post("/auth/logout")
    r = app_client.post(
        "/auth/accept-invite",
        json={"token": token, "email": "b@example.com", "password": "pw-other-1234"},
    )
    assert r.status_code == 400


def test_an_invite_cannot_be_used_twice(app_client, make_user):
    make_user(email="admin3@example.com", is_admin=True)
    _login(app_client, "admin3@example.com")
    token = app_client.post("/invites", json={}).json()["token"]
    app_client.post("/auth/logout")
    body = {"token": token, "email": "one@example.com", "password": "pw-one-12345"}
    assert app_client.post("/auth/accept-invite", json=body).status_code == 201
    body2 = {"token": token, "email": "two@example.com", "password": "pw-two-12345"}
    assert app_client.post("/auth/accept-invite", json=body2).status_code == 400


def test_unknown_invite_token_is_rejected(app_client):
    r = app_client.post(
        "/auth/accept-invite",
        json={"token": "nonsense", "email": "x@example.com", "password": "pw-x-1234567"},
    )
    assert r.status_code == 400


def test_expired_invite_is_rejected(app_client, db, make_user):
    make_user(email="admin4@example.com", is_admin=True)
    _login(app_client, "admin4@example.com")
    token = app_client.post("/invites", json={}).json()["token"]
    db.query(Invite).one().expires_at = datetime.now(UTC) - timedelta(days=1)
    db.flush()
    app_client.post("/auth/logout")
    r = app_client.post(
        "/auth/accept-invite",
        json={"token": token, "email": "late@example.com", "password": "pw-late-1234"},
    )
    assert r.status_code == 400
