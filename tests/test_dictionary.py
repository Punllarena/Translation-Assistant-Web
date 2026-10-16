import gzip
import os
from pathlib import Path

import pytest

from api import dictionary
from api.config import get_settings
from api.mt import jparser

FX = Path(__file__).parent / "fixtures" / "mt"
EDICT = (FX / "edict2_sample").read_bytes()
CONJ = (FX / "conjugations_sample.json").read_bytes()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "edict_path", "")
    monkeypatch.setattr(get_settings(), "conjugations_path", "")
    monkeypatch.setattr(dictionary, "MIN_EDICT_ENTRIES", 1)  # the sample is a few lines
    return tmp_path


@pytest.fixture
def admin(app_client, make_user, login):
    make_user(email="admin@example.com", is_admin=True)
    login(app_client, "admin@example.com")


def test_resolution_prefers_env_then_data_dir(data_dir, monkeypatch):
    assert dictionary.resolve("edict") == ("", None)
    dictionary.install("edict", EDICT)
    assert dictionary.resolve("edict") == (str(data_dir / "dict" / "edict2"), "data_dir")
    monkeypatch.setattr(get_settings(), "edict_path", "/srv/edict2")
    assert dictionary.resolve("edict") == ("/srv/edict2", "env")


def test_upload_plain_and_gzip_edict(app_client, admin, data_dir):
    for body in (EDICT, gzip.compress(EDICT)):
        r = app_client.post("/admin/dictionary/edict", files={"file": ("edict2", body)})
        assert r.status_code == 200 and r.json()["present"] and r.json()["entries"] > 0
    assert (data_dir / "dict" / "edict2").read_bytes() == EDICT


def test_garbage_edict_is_422_and_the_old_file_stays(app_client, admin, data_dir):
    dictionary.install("edict", EDICT)
    r = app_client.post("/admin/dictionary/edict", files={"file": ("x", b"not a dictionary\n")})
    assert r.status_code == 422
    assert (data_dir / "dict" / "edict2").read_bytes() == EDICT
    assert list((data_dir / "dict").iterdir()) == [data_dir / "dict" / "edict2"]  # no temp left


def test_gzip_bomb_is_refused(data_dir, monkeypatch):
    monkeypatch.setattr(dictionary, "MAX_EDICT_BYTES", 1024)
    with pytest.raises(ValueError, match="larger than"):
        dictionary.gunzip_capped(gzip.compress(b"a" * 4096))


def test_conjugations_upload_is_validated(app_client, admin, data_dir):
    assert app_client.post("/admin/dictionary/conjugations",
                           files={"file": ("c.txt", b"[]")}).status_code == 422
    r = app_client.post("/admin/dictionary/conjugations", files={"file": ("c.txt", CONJ)})
    assert r.status_code == 200 and r.json()["entries"] > 0


def test_status_and_remove(app_client, admin, data_dir):
    dictionary.install("edict", EDICT)
    body = app_client.get("/admin/dictionary").json()
    assert body["edict"]["source"] == "data_dir" and body["edict"]["size"] == len(EDICT)
    assert body["conjugations"] == {"present": False, "source": None, "size": None,
                                    "updated_at": None, "entries": None}
    assert app_client.delete("/admin/dictionary/edict").status_code == 204
    assert app_client.delete("/admin/dictionary/edict").status_code == 204
    assert app_client.get("/admin/dictionary").json()["edict"]["present"] is False


def test_env_pointed_file_cannot_be_replaced_or_removed(app_client, admin, data_dir, monkeypatch):
    monkeypatch.setattr(get_settings(), "edict_path", str(FX / "edict2_sample"))
    assert app_client.post("/admin/dictionary/edict",
                           files={"file": ("e", EDICT)}).status_code == 409
    assert app_client.delete("/admin/dictionary/edict").status_code == 409
    assert app_client.get("/admin/dictionary").json()["edict"]["source"] == "env"


def test_jparser_reloads_a_replaced_file(data_dir):
    dictionary.install("edict", EDICT)
    p = dictionary.path("edict")
    first = jparser.load_index(p)
    Path(p).write_bytes(EDICT + "追加 [ついか] /(n) addition/\n".encode("euc-jp"))
    os.utime(p, ns=(1, 1))  # a different mtime even on coarse filesystems
    assert jparser.load_index(p) is not first
    assert "追加" in jparser.load_index(p)


def test_non_admin_is_403(app_client, me):
    assert app_client.get("/admin/dictionary").status_code == 403
