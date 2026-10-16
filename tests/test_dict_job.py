import gzip
from contextlib import contextmanager
from pathlib import Path

import httpx
import pytest

from api import dict_job, dictionary, jobs
from api.config import get_settings

EDICT = (Path(__file__).parent / "fixtures" / "mt" / "edict2_sample").read_bytes()


@pytest.fixture
def env(tmp_path, monkeypatch, db, app_client, make_user, login):
    monkeypatch.setattr(get_settings(), "data_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "edict_path", "")
    monkeypatch.setattr(dictionary, "MIN_EDICT_ENTRIES", 1)

    @contextmanager
    def session():
        yield db
    monkeypatch.setattr(jobs, "SessionLocal", session)
    make_user(email="admin@example.com", is_admin=True)
    login(app_client, "admin@example.com")
    served = {"handler": lambda req: httpx.Response(200, content=gzip.compress(EDICT))}
    monkeypatch.setattr(dict_job, "http_client", lambda: httpx.Client(
        transport=httpx.MockTransport(lambda req: served["handler"](req)), follow_redirects=False))
    return served


def run(client):
    r = client.post("/admin/dictionary/edict/download")
    assert r.status_code == 202
    assert jobs.run_next() is True
    return client.get(f"/jobs/{r.json()['id']}").json()


def test_download_installs_the_dictionary(app_client, env, tmp_path):
    job = run(app_client)
    assert job["state"] == "done" and job["result"]["entries"] > 0
    assert (tmp_path / "dict" / "edict2").read_bytes() == EDICT


def test_no_internet_fails_readably_and_keeps_the_old_file(app_client, env, tmp_path):
    dictionary.install("edict", EDICT)

    def offline(req):
        raise httpx.ConnectError("no route to host")
    env["handler"] = offline
    job = run(app_client)
    assert job["state"] == "failed" and "could not reach edrdg.org" in job["message"]
    assert (tmp_path / "dict" / "edict2").read_bytes() == EDICT


@pytest.mark.parametrize("response,needle", [
    (httpx.Response(302, headers={"location": "http://elsewhere"}), "answered 302"),
    (httpx.Response(200, content=b"<html>maintenance</html>"), "EDICT2"),
])
def test_bad_responses_fail(app_client, env, response, needle):
    env["handler"] = lambda req: response
    job = run(app_client)
    assert job["state"] == "failed" and needle in job["message"]


def test_oversize_download_fails(app_client, env, monkeypatch):
    monkeypatch.setattr(dict_job, "MAX_DOWNLOAD", 10)
    job = run(app_client)
    assert job["state"] == "failed" and "larger than" in job["message"]


def test_second_download_while_one_is_queued_is_409(app_client, env):
    assert app_client.post("/admin/dictionary/edict/download").status_code == 202
    assert app_client.post("/admin/dictionary/edict/download").status_code == 409
