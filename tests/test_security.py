import hashlib
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, func, insert, select
from sqlalchemy.orm import sessionmaker

from api import deps, security
from api.security import (
    LoginLimiter,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    new_token,
    token_hash,
    verify_password,
)


def test_password_round_trip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert h.startswith("$argon2")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)


def test_each_hash_is_salted_differently():
    assert hash_password("same") != hash_password("same")


def test_verify_password_returns_false_for_malformed_hash():
    assert verify_password("anything", "not-a-hash") is False


def test_tokens_are_unguessable_and_hash_to_hex():
    t1, t2 = new_token(), new_token()
    assert t1 != t2
    assert len(t1) >= 43
    h = token_hash(t1)
    assert len(h) == 64 and h == h.lower()
    assert token_hash(t1) == h  # deterministic


def test_token_hash_accepts_non_ascii_and_empty_and_lone_surrogate():
    assert len(token_hash("é")) == 64
    assert token_hash("") == hashlib.sha256(b"").hexdigest()
    assert len(token_hash("\ud800")) == 64
    assert token_hash("\ud800") != token_hash("é")


def test_secret_round_trip_and_ciphertext_differs():
    blob = encrypt_secret("deepl-api-key-123")
    assert isinstance(blob, bytes)
    assert b"deepl-api-key-123" not in blob
    assert decrypt_secret(blob) == "deepl-api-key-123"


def test_decrypt_rejects_mid_payload_tampering():
    blob = bytearray(encrypt_secret("x"))
    mid = len(blob) // 2
    # Swap to another base64url character so the token still decodes and only HMAC can reject it.
    blob[mid] = ord("A") if blob[mid] != ord("A") else ord("B")
    with pytest.raises(ValueError):
        decrypt_secret(bytes(blob))


def test_decrypt_rejects_garbage_bytes():
    with pytest.raises(ValueError):
        decrypt_secret(b"not-a-fernet-token")


def test_decrypt_rejects_blob_from_another_key(monkeypatch):
    blob = encrypt_secret("x")
    monkeypatch.setattr(
        security, "get_settings",
        lambda: SimpleNamespace(secret_key="a-different-secret-key-at-least-32-chars"),
    )
    with pytest.raises(ValueError):
        decrypt_secret(blob)


def test_login_limiter_blocks_after_max_attempts():
    limiter = LoginLimiter(max_attempts=3, window_seconds=300)
    assert limiter.check("1.2.3.4")
    for _ in range(3):
        limiter.record_failure("1.2.3.4")
    assert not limiter.check("1.2.3.4")
    assert limiter.check("5.6.7.8")  # per-key, not global


def test_login_limiter_reset_clears_blocked_key():
    limiter = LoginLimiter(max_attempts=2, window_seconds=300)
    limiter.record_failure("k")
    limiter.record_failure("k")
    assert not limiter.check("k")
    limiter.reset("k")
    assert limiter.check("k")


def test_login_limiter_unblocks_after_window_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr(security, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    limiter = LoginLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("k")
    limiter.record_failure("k")
    assert not limiter.check("k")
    clock[0] += 61
    assert limiter.check("k")


def test_login_limiter_check_does_not_insert_unseen_keys():
    limiter = LoginLimiter(max_attempts=2, window_seconds=300)
    for i in range(50):
        assert limiter.check(f"ip-{i}")
    assert limiter._failures == {}


def test_login_limiter_evicts_stalest_keys_over_cap(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(security, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    monkeypatch.setattr(security, "MAX_TRACKED_KEYS", 3)
    limiter = LoginLimiter(max_attempts=5, window_seconds=1000)
    for i, key in enumerate(["a", "b", "c", "d"]):
        clock[0] = float(i)
        limiter.record_failure(key)
    assert set(limiter._failures) == {"b", "c", "d"}  # "a" was stalest


@pytest.fixture
def items_table(engine):
    md = MetaData()
    table = Table(
        "security_test_items", md,
        Column("id", Integer, primary_key=True), Column("name", String),
    )
    md.drop_all(engine, checkfirst=True)
    md.create_all(engine)
    try:
        yield table
    finally:
        md.drop_all(engine)


def test_db_session_parks_the_session_and_discards_uncommitted_work(
    engine, items_table, monkeypatch
):
    """The commit moved to CommitOnResponseRoute (see api/routing.py); this teardown
    runs after the response is sent, so it only rolls back and closes."""
    from api.routing import SESSION_STATE_ATTR

    monkeypatch.setattr(deps, "SessionLocal", sessionmaker(bind=engine))
    request = SimpleNamespace(state=SimpleNamespace())

    def count() -> int:
        # Independent connection: reads only what has been committed.
        with engine.connect() as conn:
            return conn.execute(select(func.count()).select_from(items_table)).scalar_one()

    gen = deps.db_session(request)
    session = next(gen)
    assert getattr(request.state, SESSION_STATE_ATTR) is session  # what the route commits
    session.execute(insert(items_table).values(name="never committed"))
    assert next(gen, None) is None  # normal exit: no commit any more
    assert count() == 0

    gen = deps.db_session(request)
    session = next(gen)
    session.execute(insert(items_table).values(name="kept"))
    session.commit()  # stands in for the route class
    assert next(gen, None) is None  # teardown's rollback is a no-op after the commit
    assert count() == 1

    gen = deps.db_session(request)
    session = next(gen)
    session.execute(insert(items_table).values(name="discarded"))
    with pytest.raises(RuntimeError):
        gen.throw(RuntimeError("boom"))
    assert count() == 1  # rollback discarded the third insert
