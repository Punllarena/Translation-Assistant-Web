import pytest


def test_get_another_users_profile_is_404(app_client, other_users_profile_id):
    assert app_client.get(f"/profiles/{other_users_profile_id}").status_code == 404


def test_patch_another_users_profile_is_404(app_client, other_users_profile_id):
    r = app_client.patch(f"/profiles/{other_users_profile_id}", json={"name": "stolen"})
    assert r.status_code == 404


def test_delete_another_users_profile_is_404(app_client, other_users_profile_id):
    assert app_client.delete(f"/profiles/{other_users_profile_id}").status_code == 404


def test_missing_id_is_also_404_not_403(app_client, make_user, login):
    make_user(email="nobody@example.com")
    login(app_client, "nobody@example.com")
    assert app_client.get("/profiles/999999").status_code == 404


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [("get", {}), ("patch", {"json": {"name": "x"}}), ("delete", {})],
)
def test_wrong_owner_and_missing_are_indistinguishable(
    app_client, other_users_profile_id, method, kwargs
):
    wrong = getattr(app_client, method)(f"/profiles/{other_users_profile_id}", **kwargs)
    missing = getattr(app_client, method)("/profiles/999999", **kwargs)
    assert wrong.status_code == missing.status_code == 404
    assert wrong.content == missing.content


def test_failed_cross_user_patch_changes_nothing(app_client, other_users_profile_id, login):
    app_client.patch(f"/profiles/{other_users_profile_id}", json={"name": "stolen"})
    app_client.post("/auth/logout")
    login(app_client, "owner@example.com")
    assert [p["name"] for p in app_client.get("/profiles").json()] == ["owned"]


def test_cross_user_delete_leaves_row_intact(app_client, db, other_users_profile_id):
    from api.models import Profile

    app_client.delete(f"/profiles/{other_users_profile_id}")
    assert db.get(Profile, other_users_profile_id) is not None


def test_scoped_rejects_model_without_user_id(db):
    from api.deps import scoped
    from api.models import MtCache

    # Row existence is irrelevant: a missing row would 404, so insert one.
    row = MtCache(**{c.name: _dummy(c) for c in MtCache.__table__.columns if not c.nullable
                     and c.server_default is None and not c.primary_key})
    db.add(row)
    db.flush()
    with pytest.raises(AttributeError):
        scoped(db, MtCache, row.id, 1)


def _dummy(column):
    from sqlalchemy import Integer

    return 1 if isinstance(column.type, Integer) else "x"
