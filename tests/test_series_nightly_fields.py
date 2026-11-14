from sqlalchemy import text


def test_new_series_defaults(db, make_user, make_series):
    s = make_series(make_user())
    db.refresh(s)
    assert s.syosetu_nightly is True and s.syosetu_fetched_through == 0
    assert s.syosetu_checked_at is None and s.syosetu_check_error == ""


def test_patch_and_read_nightly_flag(app_client, me, make_series):
    s = make_series(me)
    r = app_client.patch(f"/series/{s.id}", json={"syosetu_nightly": False})
    assert r.status_code == 200 and r.json()["syosetu_nightly"] is False
    out = app_client.get(f"/series/{s.id}").json()
    assert out["syosetu_nightly"] is False
    assert {"syosetu_fetched_through", "syosetu_checked_at", "syosetu_check_error"} <= out.keys()


def test_nightly_flag_cannot_be_null(app_client, me, make_series):
    s = make_series(me)
    assert app_client.patch(f"/series/{s.id}", json={"syosetu_nightly": None}).status_code == 422


def test_existing_rows_get_null_mark(db):
    """No server default on the mark, so the migration leaves rows from before it NULL."""
    rows = dict(db.execute(text(
        "SELECT column_name, column_default FROM information_schema.columns "
        "WHERE table_name = 'series' AND column_name IN "
        "('syosetu_fetched_through', 'syosetu_nightly', 'syosetu_check_error')")).all())
    assert rows["syosetu_fetched_through"] is None
    assert rows["syosetu_nightly"] == "true" and rows["syosetu_check_error"].startswith("''")


def test_another_novel_unseeds_the_mark(app_client, me, make_series, db):
    s = make_series(me)
    s.syosetu_url, s.syosetu_fetched_through, s.syosetu_check_error = (
        "https://ncode.syosetu.com/n1/", 40, "boom")
    db.flush()
    app_client.patch(f"/series/{s.id}", json={"syosetu_url": "https://ncode.syosetu.com/n2/"})
    db.refresh(s)
    assert s.syosetu_fetched_through is None and s.syosetu_check_error == ""


def test_a_first_url_keeps_the_mark(app_client, me, make_series, db):
    s = make_series(me)
    app_client.patch(f"/series/{s.id}", json={"syosetu_url": "https://ncode.syosetu.com/n1/"})
    db.refresh(s)
    assert s.syosetu_fetched_through == 0
