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


def _mint(client, make_user, admin_email, **body):
    make_user(email=admin_email, is_admin=True)
    _login(client, admin_email)
    token = client.post("/invites", json=body).json()["token"]
    client.post("/auth/logout")
    return token


def _accept(client, token, email, password="pw-accept-1234"):
    return client.post(
        "/auth/accept-invite", json={"token": token, "email": email, "password": password}
    )


def test_already_claimed_invite_is_rejected_and_creates_no_user(app_client, db, make_user):
    token = _mint(app_client, make_user, "admin7@example.com")
    db.query(Invite).one().accepted_at = datetime.now(UTC)
    db.flush()
    assert _accept(app_client, token, "claimed@example.com").status_code == 400
    assert db.query(User).filter_by(email="claimed@example.com").count() == 0


def test_same_token_twice_in_sequence_yields_exactly_one_user(app_client, db, make_user):
    token = _mint(app_client, make_user, "admin8@example.com")
    assert _accept(app_client, token, "first@example.com").status_code == 201
    assert _accept(app_client, token, "second@example.com").status_code == 400
    assert db.query(User).filter(User.email.in_(["first@example.com", "second@example.com"])).count() == 1
    assert db.query(Invite).one().accepted_at is not None


def test_taken_email_is_rejected_and_invite_stays_usable(app_client, db, make_user):
    token = _mint(app_client, make_user, "admin9@example.com")
    make_user(email="taken@example.com")
    assert _accept(app_client, token, "taken@example.com").status_code == 400
    assert db.query(Invite).one().accepted_at is None
    assert _accept(app_client, token, "free@example.com").status_code == 201


def test_email_unique_race_becomes_generic_400_and_releases_invite(
    app_client, db, make_user, monkeypatch
):
    """Simulate losing the users.email race: the pre-check passes, the insert collides."""
    token = _mint(app_client, make_user, "admin10@example.com")
    make_user(email="raced@example.com")
    real_scalar = db.scalar
    calls = {"n": 0}

    def scalar_skipping_user_lookup(stmt, *a, **k):
        if "FROM users" in str(stmt):
            calls["n"] += 1
            return None
        return real_scalar(stmt, *a, **k)

    monkeypatch.setattr(db, "scalar", scalar_skipping_user_lookup)
    r = _accept(app_client, token, "raced@example.com")
    monkeypatch.undo()
    assert calls["n"] == 1
    assert r.status_code == 400
    assert db.query(Invite).one().accepted_at is None  # claim rolled back with the savepoint


def test_every_rejection_path_returns_the_same_body(app_client, db, make_user):
    bodies = []
    # unknown token
    bodies.append(_accept(app_client, "nonsense", "u1@example.com"))
    # already used
    t = _mint(app_client, make_user, "admin11@example.com")
    _accept(app_client, t, "used@example.com")
    bodies.append(_accept(app_client, t, "u2@example.com"))
    # expired
    t = _mint(app_client, make_user, "admin12@example.com")
    inv = db.query(Invite).filter(Invite.accepted_at.is_(None)).one()
    inv.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.flush()
    bodies.append(_accept(app_client, t, "u3@example.com"))
    # bound to another email
    t = _mint(app_client, make_user, "admin13@example.com", email="bound@example.com")
    bodies.append(_accept(app_client, t, "u4@example.com"))
    # taken email
    t = _mint(app_client, make_user, "admin14@example.com")
    bodies.append(_accept(app_client, t, "used@example.com"))
    assert [r.status_code for r in bodies] == [400] * 5
    assert len({str(r.json()) for r in bodies}) == 1
