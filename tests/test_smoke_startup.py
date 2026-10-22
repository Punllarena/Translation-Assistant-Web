from api.main import create_app


def test_every_phase1_route_is_registered():
    schema = create_app().openapi()
    assert schema["info"]["title"] == "ta-web"
    paths = set(schema["paths"])
    expected = {
        "/healthz",
        "/auth/login", "/auth/logout", "/auth/me", "/auth/accept-invite",
        "/invites",
        "/settings", "/settings/{key}",
        "/shortcuts", "/shortcuts/{action_key}",
        "/credentials", "/credentials/{credential_id}",
    }
    assert expected <= paths
    assert not any(p.startswith("/profiles") for p in paths)

