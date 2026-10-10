from api.main import create_app


def test_every_phase1_route_is_registered():
    paths = set(create_app().openapi()["paths"])
    expected = {
        "/healthz",
        "/auth/login", "/auth/logout", "/auth/me", "/auth/accept-invite",
        "/invites",
        "/profiles", "/profiles/{profile_id}",
        "/settings", "/settings/{key}",
        "/shortcuts", "/shortcuts/{action_key}",
        "/credentials", "/credentials/{credential_id}",
    }
    assert expected <= paths


def test_openapi_schema_builds():
    schema = create_app().openapi()
    assert schema["info"]["title"] == "ta-web"
    assert "/auth/login" in schema["paths"]
