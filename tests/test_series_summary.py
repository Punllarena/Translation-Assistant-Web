def test_saving_a_summary_marks_it_pending(app_client, me, make_series):
    s = make_series(me, "Sword")
    r = app_client.patch(f"/series/{s.id}", json={"wp_summary": "First.\n\nSecond."})
    assert r.status_code == 200
    body = r.json()
    assert (body["wp_summary"], body["wp_summary_pending"], body["wp_summary_error"]) == (
        "First.\n\nSecond.",
        True,
        "",
    )


def test_blank_summary_is_not_pending_and_clears_the_error(app_client, me, make_series, db):
    s = make_series(me, "Sword")
    s.wp_summary, s.wp_summary_pending, s.wp_summary_error = "x", True, "boom"
    db.flush()
    body = app_client.patch(f"/series/{s.id}", json={"wp_summary": "  \n "}).json()
    assert (body["wp_summary_pending"], body["wp_summary_error"]) == (False, "")


def test_unchanged_summary_keeps_its_state(app_client, me, make_series, db):
    s = make_series(me, "Sword")
    s.wp_summary, s.wp_summary_pending = "same", False
    db.flush()
    body = app_client.patch(f"/series/{s.id}", json={"wp_summary": "same"}).json()
    assert body["wp_summary_pending"] is False


def test_other_fields_leave_the_summary_alone(app_client, me, make_series, db):
    s = make_series(me, "Sword")
    s.wp_summary, s.wp_summary_pending, s.wp_summary_error = "x", True, "boom"
    db.flush()
    body = app_client.patch(f"/series/{s.id}", json={"wp_series_slug": "sword"}).json()
    assert (body["wp_summary_pending"], body["wp_summary_error"]) == (True, "boom")


def test_summary_nul_and_length_are_422(app_client, me, make_series):
    s = make_series(me, "Sword")
    assert app_client.patch(f"/series/{s.id}", json={"wp_summary": "a\x00b"}).status_code == 422
    big = "a" * 100_001
    assert app_client.patch(f"/series/{s.id}", json={"wp_summary": big}).status_code == 422


def test_another_users_series_is_404(app_client, me, make_user, make_series):
    other = make_series(make_user(email="o@example.com"), "Theirs")
    assert app_client.patch(f"/series/{other.id}", json={"wp_summary": "x"}).status_code == 404
