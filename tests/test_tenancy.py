import pytest


def _login(client, email, password="pw-correct"):
    client.post("/auth/login", json={"email": email, "password": password})


@pytest.fixture
def other_users_profile_id(app_client, make_user):
    make_user(email="owner@example.com")
    make_user(email="intruder@example.com")
    _login(app_client, "owner@example.com")
    pid = app_client.post("/profiles", json={"name": "owned"}).json()["id"]
    app_client.post("/auth/logout")
    _login(app_client, "intruder@example.com")
    return pid


def test_get_another_users_profile_is_404(app_client, other_users_profile_id):
    assert app_client.get(f"/profiles/{other_users_profile_id}").status_code == 404


def test_patch_another_users_profile_is_404(app_client, other_users_profile_id):
    r = app_client.patch(f"/profiles/{other_users_profile_id}", json={"name": "stolen"})
    assert r.status_code == 404


def test_delete_another_users_profile_is_404(app_client, other_users_profile_id):
    assert app_client.delete(f"/profiles/{other_users_profile_id}").status_code == 404


def test_missing_id_is_also_404_not_403(app_client, make_user):
    make_user(email="nobody@example.com")
    _login(app_client, "nobody@example.com")
    assert app_client.get("/profiles/999999").status_code == 404


def test_wrong_owner_and_missing_are_indistinguishable(app_client, other_users_profile_id):
    wrong = app_client.get(f"/profiles/{other_users_profile_id}")
    missing = app_client.get("/profiles/999999")
    assert (wrong.status_code, wrong.json()) == (missing.status_code, missing.json())


def test_failed_cross_user_patch_changes_nothing(app_client, other_users_profile_id):
    app_client.patch(f"/profiles/{other_users_profile_id}", json={"name": "stolen"})
    app_client.post("/auth/logout")
    _login(app_client, "owner@example.com")
    assert [p["name"] for p in app_client.get("/profiles").json()] == ["owned"]
