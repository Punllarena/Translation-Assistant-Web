"""The branding routes: a public read, admin-only writes, and the sandboxed image route."""

import pytest

from api import branding
from api.backup import crypto, export, restore
from api.models import Branding

PASS = "correct horse battery"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
PNG_BIG = b"\x89PNG\r\n\x1a\n" + b"\x00" * (1024 * 1024 - 8)
ICO = b"\x00\x00\x01\x00" + b"\x00" * 16
JPEG = b"\xff\xd8\xff" + b"\x00" * 16
SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'
HTML = b"<html><body><svg></svg></body></html>"
DEFAULTS = {
    "name": "Translation Assistant",
    "show_name": True,
    "logo_id": None,
    "logo_dark_id": None,
    "favicon_id": None,
}


@pytest.fixture
def admin(app_client, make_user, login):
    make_user(email="admin@example.com", is_admin=True)
    login(app_client, "admin@example.com")
    return app_client


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "edict_path", "")
    monkeypatch.setattr(get_settings(), "conjugations_path", "")
    return tmp_path


def _upload(client, kind, data, name="x.png"):
    return client.put(f"/admin/branding/{kind}", files={"file": (name, data, "image/png")})


def test_public_get_needs_no_login(app_client):
    r = app_client.get("/branding")
    assert r.status_code == 200
    assert r.json() == DEFAULTS


def test_non_admin_and_signed_out_cannot_write(app_client, make_user, login):
    body = {"name": "Mine", "show_name": True}
    assert app_client.put("/admin/branding", json=body).status_code == 401
    assert _upload(app_client, "logo", PNG).status_code == 401
    assert app_client.delete("/admin/branding/logo").status_code == 401
    assert app_client.delete("/admin/branding").status_code == 401

    make_user(email="plain@example.com")
    login(app_client, "plain@example.com")
    assert app_client.put("/admin/branding", json=body).status_code == 403
    assert _upload(app_client, "logo", PNG).status_code == 403
    assert app_client.delete("/admin/branding/logo").status_code == 403
    assert app_client.delete("/admin/branding").status_code == 403
    assert app_client.get("/branding").json() == DEFAULTS


def test_set_text_and_read_back(admin):
    r = admin.put("/admin/branding", json={"name": "  My Site  ", "show_name": False})
    assert r.status_code == 200
    assert r.json() == {**DEFAULTS, "name": "My Site", "show_name": False}
    assert admin.get("/branding").json() == r.json()


def test_blank_name_reads_back_as_default(admin, db):
    assert admin.put("/admin/branding", json={"name": "   ", "show_name": True}).status_code == 200
    assert admin.get("/branding").json()["name"] == "Translation Assistant"
    assert db.get(Branding, 1).name is None  # stored blank, never an empty brand


def test_name_over_60_is_422(admin):
    r = admin.put("/admin/branding", json={"name": "x" * 61, "show_name": True})
    assert r.status_code == 422
    assert admin.get("/branding").json()["name"] == "Translation Assistant"


def test_upload_logo_favicon_and_serve(admin, app_client):
    r = _upload(admin, "logo", PNG)
    assert r.status_code == 200
    logo_id = r.json()["logo_id"]
    fav = _upload(admin, "favicon", ICO)
    assert fav.status_code == 200
    assert fav.json()["favicon_id"] is not None

    img = app_client.get(f"/branding/image/{logo_id}")
    assert img.status_code == 200 and img.content == PNG
    assert img.headers["content-type"] == "image/png"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in img.headers["content-security-policy"]
    assert "immutable" in img.headers["cache-control"]

    icon = app_client.get(f"/branding/image/{fav.json()['favicon_id']}")
    assert icon.headers["content-type"] == "image/x-icon"


def test_svg_with_script_served_sandboxed(admin, app_client):
    r = _upload(admin, "logo", SVG, "x.svg")
    assert r.status_code == 200
    img = app_client.get(f"/branding/image/{r.json()['logo_id']}")
    assert img.headers["content-type"] == "image/svg+xml"
    assert img.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in img.headers["content-security-policy"]


def test_upload_rejections(admin):
    assert _upload(admin, "logo", JPEG, "x.jpg").status_code == 415
    assert "PNG" in _upload(admin, "logo", JPEG, "x.jpg").json()["detail"]
    assert _upload(admin, "logo", HTML, "x.svg").status_code == 415
    assert _upload(admin, "logo", ICO).status_code == 415
    assert _upload(admin, "nope", PNG).status_code == 404
    assert admin.get("/branding").json() == DEFAULTS


def test_exactly_1mib_ok_and_one_over_is_413(admin):
    assert _upload(admin, "logo", PNG_BIG).status_code == 200
    assert _upload(admin, "logo", PNG_BIG + b"x").status_code == 413


def test_replace_changes_id_and_old_id_is_404(admin, app_client):
    first = _upload(admin, "logo", PNG).json()["logo_id"]
    second = _upload(admin, "logo", PNG + b"changed").json()["logo_id"]
    assert second != first
    assert app_client.get(f"/branding/image/{first}").status_code == 404
    assert app_client.get(f"/branding/image/{second}").content == PNG + b"changed"


def test_delete_kind_is_idempotent(admin):
    _upload(admin, "logo", PNG)
    assert admin.delete("/admin/branding/logo").status_code == 204
    assert admin.get("/branding").json()["logo_id"] is None
    assert admin.delete("/admin/branding/logo").status_code == 204
    assert admin.delete("/admin/branding/nope").status_code == 404


def test_reset_restores_defaults(admin):
    admin.put("/admin/branding", json={"name": "Mine", "show_name": False})
    _upload(admin, "logo", PNG)
    _upload(admin, "favicon", ICO)

    assert admin.delete("/admin/branding").status_code == 204
    assert admin.get("/branding").json() == DEFAULTS


def test_survives_backup_round_trip(admin, app_client, db, tmp_path, data_dir):
    admin.put("/admin/branding", json={"name": "Mine", "show_name": False})
    logo_id = _upload(admin, "logo", PNG).json()["logo_id"]
    favicon_id = _upload(admin, "favicon", ICO).json()["favicon_id"]

    kdf = crypto.new_kdf()
    path = tmp_path / "b.zip"
    with path.open("wb") as out:
        export.write(db.connection(), out, crypto.derive(PASS, kdf), kdf)

    reader = restore.BackupReader.open(path, PASS)
    conn = db.connection()
    with conn.begin_nested():
        restore.apply(conn, reader, from_setup=False, progress=lambda *args: None)
    reader.close()
    db.expire_all()

    body = app_client.get("/branding").json()
    assert body == {**DEFAULTS, "name": "Mine", "show_name": False,
                    "logo_id": logo_id, "favicon_id": favicon_id}
    assert app_client.get(f"/branding/image/{logo_id}").content == PNG
    assert app_client.get(f"/branding/image/{favicon_id}").content == ICO
    assert branding.media_type(ICO) == "image/x-icon"
