import pytest


def test_get_another_users_series_is_404(app_client, other_users_series_id):
    assert app_client.get(f"/series/{other_users_series_id}").status_code == 404


def test_patch_another_users_series_is_404(app_client, other_users_series_id):
    r = app_client.patch(f"/series/{other_users_series_id}", json={"title": "stolen"})
    assert r.status_code == 404


def test_delete_another_users_series_is_404(app_client, other_users_series_id):
    assert app_client.delete(f"/series/{other_users_series_id}").status_code == 404


def test_missing_id_is_also_404_not_403(app_client, make_user, login):
    make_user(email="nobody@example.com")
    login(app_client, "nobody@example.com")
    assert app_client.get("/series/999999").status_code == 404


@pytest.mark.parametrize(
    ("method", "kwargs"),
    [("get", {}), ("patch", {"json": {"title": "x"}}), ("delete", {})],
)
def test_wrong_owner_and_missing_are_indistinguishable(
    app_client, other_users_series_id, method, kwargs
):
    wrong = getattr(app_client, method)(f"/series/{other_users_series_id}", **kwargs)
    missing = getattr(app_client, method)("/series/999999", **kwargs)
    assert wrong.status_code == missing.status_code == 404
    assert wrong.content == missing.content


def test_failed_cross_user_patch_changes_nothing(app_client, other_users_series_id, login):
    app_client.patch(f"/series/{other_users_series_id}", json={"title": "stolen"})
    app_client.post("/auth/logout")
    login(app_client, "owner@example.com")
    assert [s["title"] for s in app_client.get("/series").json()] == ["owned"]


def test_cross_user_delete_leaves_row_intact(app_client, db, other_users_series_id):
    from api.models import Series

    app_client.delete(f"/series/{other_users_series_id}")
    assert db.get(Series, other_users_series_id) is not None


@pytest.mark.parametrize(
    ("method", "tail", "kwargs"),
    [
        ("get", "/glossary", {}),
        ("post", "/glossary/import", {"files": {"file": ("g.csv", b"a,b", "text/csv")}}),
        ("get", "/words", {}),
        ("put", "/words/w", {}),
        ("delete", "/words/w", {}),
    ],
)
def test_another_users_series_glossary_and_words_are_404(
    app_client, db, other_users_series_id, method, tail, kwargs
):
    from sqlalchemy import select

    from api.models import CustomWord, GlossaryEntry

    r = getattr(app_client, method)(f"/series/{other_users_series_id}{tail}", **kwargs)
    assert r.status_code == 404
    assert db.scalars(select(GlossaryEntry)).all() == []
    assert db.scalars(select(CustomWord)).all() == []


def test_scoped_rejects_model_without_user_id(db):
    """The check precedes the lookup, so even a non-existent id is loud."""
    from api.deps import scoped
    from api.models import MtCache

    with pytest.raises(AttributeError, match="user_id"):
        scoped(db, MtCache, 999999, 1)
