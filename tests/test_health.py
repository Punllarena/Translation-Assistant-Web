from fastapi.testclient import TestClient

from api.main import create_app


def test_healthz_reports_ok():
    client = TestClient(create_app())
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
