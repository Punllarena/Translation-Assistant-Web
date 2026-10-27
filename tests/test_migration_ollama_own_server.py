"""The data step of the ollama-own-server revision: a user who had Ollama enabled keeps the
server they were silently using, as their own credential. Runs inside the test transaction."""

import importlib.util
from pathlib import Path

from api.models import ApiCredential, ServerSetting, UserSetting
from api.security import decrypt_secret

_VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def _migration():
    (path,) = _VERSIONS.glob("*_ollama_own_server.py")
    spec = importlib.util.spec_from_file_location("mig_ollama_own_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(db):
    _migration().give_users_the_operator_url(db.connection())
    db.expire_all()


def _enable(db, user, backends):
    db.add(UserSetting(user_id=user.id, key="mt_enabled", value_json=backends))
    db.flush()


def _cred(db, user):
    return db.query(ApiCredential).filter_by(user_id=user.id, kind="ollama", name="").one_or_none()


def test_enabled_user_gets_the_operator_url_as_their_credential(db, make_user):
    user = make_user()
    _enable(db, user, ["ollama", "mecab"])
    db.add(ServerSetting(key="ollama_url", value="http://gpu.lan:11434"))
    db.flush()

    _run(db)

    cred = _cred(db, user)
    assert cred.endpoint_url == "http://gpu.lan:11434" and decrypt_secret(cred.secret_enc) == ""
    assert db.get(ServerSetting, "ollama_url") is None


def test_without_a_server_row_the_env_then_the_default_is_used(db, make_user, monkeypatch):
    user = make_user()
    _enable(db, user, ["ollama"])
    monkeypatch.delenv("TA_OLLAMA_URL", raising=False)
    _run(db)
    assert _cred(db, user).endpoint_url == "http://localhost:11434"


def test_env_url_beats_the_default(db, make_user, monkeypatch):
    user = make_user()
    _enable(db, user, ["ollama"])
    monkeypatch.setenv("TA_OLLAMA_URL", "http://env:11434")
    _run(db)
    assert _cred(db, user).endpoint_url == "http://env:11434"


def test_users_without_ollama_enabled_get_nothing(db, make_user):
    off, unset = make_user(), make_user(email="b@example.com")
    _enable(db, off, ["mecab"])
    _run(db)
    assert _cred(db, off) is None and _cred(db, unset) is None


def test_existing_own_url_is_kept_and_an_empty_one_is_filled(db, make_user):
    keeps, empty = make_user(), make_user(email="b@example.com")
    for user, url in ((keeps, "http://mine:11434"), (empty, "")):
        _enable(db, user, ["ollama"])
        db.add(ApiCredential(user_id=user.id, kind="ollama", name="", secret_enc=b"x",
                             endpoint_url=url))
    db.add(ServerSetting(key="ollama_url", value="http://gpu.lan:11434"))
    db.flush()

    _run(db)

    assert _cred(db, keeps).endpoint_url == "http://mine:11434"
    filled = _cred(db, empty)
    assert filled.endpoint_url == "http://gpu.lan:11434" and filled.secret_enc == b"x"

