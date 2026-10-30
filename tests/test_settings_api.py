import pytest


def test_settings_require_authentication(app_client):
    assert app_client.get("/settings").status_code == 401


def test_settings_start_empty(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.get("/settings").json() == {}


def test_put_settings_accepts_any_json_value(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    payload = {"font_size": 14.5, "tm_visible": True, "last_doc_id": 7, "panels": {"mt": False}}
    assert app_client.put("/settings", json=payload).json() == payload
    assert app_client.get("/settings").json() == payload


def test_put_settings_merges_rather_than_replaces(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/settings", json={"a": 1})
    assert app_client.put("/settings", json={"b": 2}).json() == {"a": 1, "b": 2}


def test_put_settings_overwrites_only_submitted_keys(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/settings", json={"a": 1, "b": 2})
    assert app_client.put("/settings", json={"a": "new"}).json() == {"a": "new", "b": 2}


def test_put_settings_accepts_json_null_value(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.put("/settings", json={"a": None}).json() == {"a": None}
    assert app_client.get("/settings").json() == {"a": None}


def test_delete_setting_is_idempotent(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/settings", json={"a": 1})
    assert app_client.delete("/settings/a").status_code == 204
    assert app_client.delete("/settings/a").status_code == 204
    assert app_client.get("/settings").json() == {}


def test_settings_are_per_user(app_client, make_user, login):
    make_user(email="s@example.com")
    make_user(email="t@example.com")
    login(app_client, "s@example.com")
    app_client.put("/settings", json={"font_size": 20})
    app_client.post("/auth/logout")
    login(app_client, "t@example.com")
    assert app_client.get("/settings").json() == {}
    app_client.put("/settings", json={"font_size": 12})
    app_client.delete("/settings/font_size")
    app_client.post("/auth/logout")
    login(app_client, "s@example.com")
    assert app_client.get("/settings").json() == {"font_size": 20}


def test_shortcuts_require_authentication(app_client):
    assert app_client.get("/shortcuts").status_code == 401


def test_shortcuts_round_trip(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    body = {"next_line": "Down", "prev_line": "Up", "find": "Ctrl+F"}
    assert app_client.put("/shortcuts", json=body).json() == body
    assert app_client.get("/shortcuts").json() == body


def test_shortcuts_are_per_user(app_client, make_user, login):
    make_user(email="s@example.com")
    make_user(email="t@example.com")
    login(app_client, "s@example.com")
    app_client.put("/shortcuts", json={"next_line": "Down"})
    app_client.post("/auth/logout")
    login(app_client, "t@example.com")
    assert app_client.get("/shortcuts").json() == {}
    # The same binding is free for another user's action.
    assert app_client.put("/shortcuts", json={"prev_line": "Down"}).status_code == 200


def test_conflicting_binding_is_409(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/shortcuts", json={"next_line": "Down"})
    r = app_client.put("/shortcuts", json={"next_paragraph": "Down"})
    assert r.status_code == 409


def test_conflict_within_one_payload_is_409(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    r = app_client.put("/shortcuts", json={"next_line": "Down", "next_paragraph": "Down"})
    assert r.status_code == 409
    assert app_client.get("/shortcuts").json() == {}


def test_conflict_is_checked_against_stored_state_not_just_payload(
    app_client, make_user, login
):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/shortcuts", json={"next_line": "Down", "prev_line": "Up"})
    # Only one key in this payload, but it collides with the stored prev_line binding.
    assert app_client.put("/shortcuts", json={"find": "Up"}).status_code == 409
    assert app_client.get("/shortcuts").json() == {"next_line": "Down", "prev_line": "Up"}


def test_rebinding_the_same_action_is_allowed(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/shortcuts", json={"next_line": "Down"})
    assert app_client.put("/shortcuts", json={"next_line": "Ctrl+Down"}).status_code == 200
    assert app_client.get("/shortcuts").json() == {"next_line": "Ctrl+Down"}


def test_freed_binding_can_be_taken_after_rebind(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/shortcuts", json={"next_line": "Down"})
    app_client.put("/shortcuts", json={"next_line": "Ctrl+Down"})
    assert app_client.put("/shortcuts", json={"next_paragraph": "Down"}).status_code == 200


def test_delete_shortcut_reverts_to_default(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/shortcuts", json={"next_line": "Down"})
    assert app_client.delete("/shortcuts/next_line").status_code == 204
    assert app_client.get("/shortcuts").json() == {}


def test_delete_absent_shortcut_is_204(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.delete("/shortcuts/next_line").status_code == 204


def test_over_long_settings_key_is_422(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.put("/settings", json={"k" * 121: 1}).status_code == 422
    assert app_client.get("/settings").json() == {}


def test_empty_settings_key_is_422(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.put("/settings", json={"": 1}).status_code == 422


def test_over_long_action_key_is_422(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.put("/shortcuts", json={"a" * 121: "Down"}).status_code == 422
    assert app_client.get("/shortcuts").json() == {}


def test_empty_action_key_is_422(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.put("/shortcuts", json={"": "Down"}).status_code == 422


def test_over_long_binding_is_422(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.put("/shortcuts", json={"next_line": "b" * 121}).status_code == 422
    assert app_client.get("/shortcuts").json() == {}


def test_empty_binding_is_422(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    assert app_client.put("/shortcuts", json={"next_line": ""}).status_code == 422


def test_swapping_bindings_within_one_payload_succeeds(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    app_client.put("/shortcuts", json={"next_line": "Down", "prev_line": "Up"})
    r = app_client.put("/shortcuts", json={"next_line": "Up", "prev_line": "Down"})
    assert r.status_code == 200
    assert r.json() == {"next_line": "Up", "prev_line": "Down"}


def test_max_length_key_and_binding_are_accepted(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    body = {"a" * 120: "b" * 120}
    assert app_client.put("/shortcuts", json=body).status_code == 200
    assert app_client.put("/settings", json={"k" * 120: 1}).status_code == 200


def test_invalid_ollama_schedule_is_422(app_client, make_user, login):
    make_user(email="s@example.com")
    login(app_client, "s@example.com")
    good = {"enabled": True, "start": "22:00", "end": "06:00", "days": [0, 1], "tz": "Asia/Manila"}
    bad = {**good, "tz": "Mars/Olympus"}
    r = app_client.put("/settings", json={"ollama_schedule": bad})
    assert r.status_code == 422
    assert app_client.get("/settings").json() == {}
    assert app_client.put("/settings", json={"ollama_schedule": good}).status_code == 200
    # null stays allowed, and so does deleting it
    assert app_client.put("/settings", json={"ollama_schedule": None}).status_code == 200
    assert app_client.delete("/settings/ollama_schedule").status_code == 204


@pytest.mark.parametrize(
    "bad", ["images", ["num", 3], ["nope"], {"a": 1}]
)
def test_series_columns_rejects_malformed(app_client, me, bad):
    assert app_client.put("/settings", json={"series_columns": bad}).status_code == 422


def test_series_columns_accepts_known_ids(app_client, me):
    r = app_client.put("/settings", json={"series_columns": ["num", "title", "images"]})
    assert r.status_code == 200 and r.json()["series_columns"] == ["num", "title", "images"]
    assert app_client.put("/settings", json={"series_columns": None}).status_code == 200


def test_library_settings_round_trip(app_client, me):
    filters = {"sources": ["epub"], "statuses": [], "wordpress": "any", "archived": "hide"}
    body = {"library_view": "list", "library_sort": {"key": "title", "dir": "asc"},
            "library_filters": filters}
    r = app_client.put("/settings", json=body)
    assert r.status_code == 200 and {k: r.json()[k] for k in body} == body


FILTERS = {"sources": [], "statuses": [], "wordpress": "any", "archived": "hide"}


@pytest.mark.parametrize("key,bad", [
    ("library_view", "grid"),
    ("library_view", ["shelf"]),
    ("library_sort", {"key": "nope", "dir": "asc"}),
    ("library_sort", {"key": "title"}),
    ("library_sort", {"key": "title", "dir": "asc", "x": 1}),
    ("library_sort", ["title", "asc"]),
    ("library_filters", {**FILTERS, "sources": ["web"]}),
    ("library_filters", {**FILTERS, "statuses": ["paused"]}),
    ("library_filters", {**FILTERS, "wordpress": "maybe"}),
    ("library_filters", {**FILTERS, "archived": "some"}),
    ("library_filters", {"sources": [], "statuses": []}),
    ("library_filters", {**FILTERS, "sources": ["epub", 2]}),
    ("library_filters", {**FILTERS, "x": 1}),
    ("library_filters", "hide"),
])
def test_library_settings_rejected(app_client, me, key, bad):
    assert app_client.put("/settings", json={key: bad}).status_code == 422


def test_schedule_rule_still_applies(app_client, me):
    r = app_client.put("/settings", json={"ollama_schedule": {"enabled": True}})
    assert r.status_code == 422
    assert "ollama_schedule needs" in r.json()["detail"]
