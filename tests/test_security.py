import pytest

from api.security import (
    LoginLimiter, decrypt_secret, encrypt_secret, hash_password, new_token,
    token_hash, verify_password,
)


def test_password_round_trip():
    h = hash_password("correct horse")
    assert h != "correct horse"
    assert h.startswith("$argon2")
    assert verify_password("correct horse", h)
    assert not verify_password("wrong horse", h)


def test_each_hash_is_salted_differently():
    assert hash_password("same") != hash_password("same")


def test_tokens_are_unguessable_and_hash_to_hex():
    t1, t2 = new_token(), new_token()
    assert t1 != t2
    assert len(t1) >= 43
    h = token_hash(t1)
    assert len(h) == 64 and h == h.lower()
    assert token_hash(t1) == h  # deterministic


def test_secret_round_trip_and_ciphertext_differs():
    blob = encrypt_secret("deepl-api-key-123")
    assert isinstance(blob, bytes)
    assert b"deepl-api-key-123" not in blob
    assert decrypt_secret(blob) == "deepl-api-key-123"


def test_decrypt_rejects_tampered_ciphertext():
    blob = bytearray(encrypt_secret("x"))
    blob[-1] ^= 0xFF
    with pytest.raises(ValueError):
        decrypt_secret(bytes(blob))


def test_login_limiter_blocks_after_max_attempts():
    limiter = LoginLimiter(max_attempts=3, window_seconds=300)
    assert limiter.check("1.2.3.4")
    for _ in range(3):
        limiter.record_failure("1.2.3.4")
    assert not limiter.check("1.2.3.4")
    assert limiter.check("5.6.7.8")  # per-key, not global
