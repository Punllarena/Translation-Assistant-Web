import logging

from api.models import ApiCredential
from api.routers.credentials import load_secret


def test_credentials_require_authentication(app_client):
    assert app_client.get("/credentials").status_code == 401


def test_create_and_list_never_exposes_the_secret(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    r = app_client.post("/credentials", json={"kind": "deepl", "secret": "abcd1234efgh5678"})
    assert r.status_code == 201
    body = r.json()
    assert "secret" not in body and "secret_enc" not in body
    assert body["has_secret"] is True
    assert body["secret_hint"] == "…5678"
    listed = app_client.get("/credentials")
    assert listed.json()[0]["secret_hint"] == "…5678"
    assert "abcd1234efgh5678" not in listed.text
    assert "abcd1234efgh5678" not in r.text


def test_short_secret_gets_no_hint(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    r = app_client.post("/credentials", json={"kind": "ollama", "secret": "abc"})
    assert r.json()["secret_hint"] == ""


def test_unknown_kind_is_rejected(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    r = app_client.post("/credentials", json={"kind": "hotmail", "secret": "x"})
    assert r.status_code == 422


def test_duplicate_kind_and_name_is_409(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    app_client.post("/credentials", json={"kind": "deepl", "name": "main", "secret": "a" * 10})
    r = app_client.post("/credentials", json={"kind": "deepl", "name": "main", "secret": "b" * 10})
    assert r.status_code == 409


def test_rename_onto_existing_name_is_409(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    app_client.post("/credentials", json={"kind": "deepl", "name": "a", "secret": "x" * 10})
    cid = app_client.post(
        "/credentials", json={"kind": "deepl", "name": "b", "secret": "y" * 10}
    ).json()["id"]
    assert app_client.patch(f"/credentials/{cid}", json={"name": "a"}).status_code == 409


def test_duplicate_is_409_and_leaves_existing_row_intact(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    app_client.post("/credentials", json={"kind": "deepl", "secret": "a" * 10})
    r = app_client.post("/credentials", json={"kind": "deepl", "secret": "b" * 10})
    assert r.status_code == 409
    listed = app_client.get("/credentials").json()
    assert len(listed) == 1 and listed[0]["secret_hint"] == "…aaaa"


def test_patch_without_secret_leaves_it_intact(app_client, db, make_user, login):
    user = make_user(email="k@example.com")
    login(app_client, "k@example.com")
    cid = app_client.post(
        "/credentials", json={"kind": "wordpress", "secret": "wp-secret-value"}
    ).json()["id"]
    r = app_client.patch(f"/credentials/{cid}", json={"endpoint_url": "https://example.com/wp-json"})
    assert r.status_code == 200
    assert "wp-secret-value" not in r.text
    assert load_secret(db, user.id, "wordpress") == "wp-secret-value"


def test_patch_with_secret_replaces_it(app_client, db, make_user, login):
    user = make_user(email="k@example.com")
    login(app_client, "k@example.com")
    cid = app_client.post("/credentials", json={"kind": "deepl", "secret": "old-secret"}).json()["id"]
    r = app_client.patch(f"/credentials/{cid}", json={"secret": "new-secret-value"})
    assert r.status_code == 200
    assert "new-secret-value" not in r.text
    assert r.json()["secret_hint"] == "…alue"
    assert load_secret(db, user.id, "deepl") == "new-secret-value"


def test_patch_rejects_explicit_nulls(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    cid = app_client.post("/credentials", json={"kind": "deepl", "secret": "a" * 10}).json()["id"]
    for field in ("name", "secret", "endpoint_url"):
        r = app_client.patch(f"/credentials/{cid}", json={field: None})
        assert r.status_code == 422, field


def test_over_long_name_and_endpoint_are_422(app_client, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    r = app_client.post(
        "/credentials", json={"kind": "deepl", "name": "n" * 121, "secret": "a" * 10}
    )
    assert r.status_code == 422
    r = app_client.post(
        "/credentials",
        json={"kind": "deepl", "endpoint_url": "https://x.test/" + "p" * 2048, "secret": "a" * 10},
    )
    assert r.status_code == 422


def test_secret_is_encrypted_at_rest(app_client, db, make_user, login):
    make_user(email="k@example.com")
    login(app_client, "k@example.com")
    app_client.post("/credentials", json={"kind": "deepl", "secret": "plaintext-xyz"})
    blob = db.query(ApiCredential).one().secret_enc
    assert b"plaintext-xyz" not in blob


def test_another_users_credential_is_404(app_client, make_user, login):
    make_user(email="k@example.com")
    make_user(email="other@example.com")
    login(app_client, "k@example.com")
    cid = app_client.post("/credentials", json={"kind": "deepl", "secret": "a" * 10}).json()["id"]
    app_client.post("/auth/logout")
    login(app_client, "other@example.com")
    assert app_client.patch(f"/credentials/{cid}", json={"name": "x"}).status_code == 404
    assert app_client.patch(f"/credentials/{cid}", json={"secret": "z" * 10}).status_code == 404
    assert app_client.delete(f"/credentials/{cid}").status_code == 404


def test_delete_own_credential(app_client, db, make_user, login):
    user = make_user(email="k@example.com")
    login(app_client, "k@example.com")
    cid = app_client.post("/credentials", json={"kind": "deepl", "secret": "a" * 10}).json()["id"]
    assert app_client.delete(f"/credentials/{cid}").status_code == 204
    assert load_secret(db, user.id, "deepl") is None


def test_undecryptable_blob_lists_as_no_secret_and_logs(
    app_client, db, make_user, login, caplog
):
    user = make_user(email="k@example.com")
    login(app_client, "k@example.com")
    db.add(ApiCredential(user_id=user.id, kind="deepl", name="", secret_enc=b"not-a-fernet"))
    db.flush()
    with caplog.at_level(logging.WARNING, logger="api.routers.credentials"):
        r = app_client.get("/credentials")
    assert r.status_code == 200
    assert r.json()[0]["has_secret"] is False
    assert r.json()[0]["secret_hint"] == ""
    assert any("could not be decrypted" in rec.getMessage() for rec in caplog.records)


def test_load_secret_returns_none_when_absent(app_client, db, make_user):
    user = make_user(email="k@example.com")
    assert load_secret(db, user.id, "deepl") is None
