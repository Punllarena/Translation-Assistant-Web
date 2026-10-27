"""The backup passphrase (KDF, check value, credential re-lock) and the manifest."""

import io
from dataclasses import replace

import pytest

from api.backup import crypto, manifest
from api.backup.crypto import WRONG_PASSPHRASE, WrongPassphrase
from api.backup.manifest import BackupInvalid
from api.models import ApiCredential
from api.security import decrypt_secret, encrypt_secret

PASS = "correct horse battery"


def _cursor(db):
    return db.connection().connection.driver_connection.cursor()


def _copy_out(db) -> bytes:
    buf = io.BytesIO()
    with _cursor(db) as cur, cur.copy(
        "COPY api_credentials TO STDOUT (FORMAT csv, HEADER)"
    ) as copy:
        for chunk in copy:
            buf.write(chunk)
    return buf.getvalue()


def _copy_in(db, data: bytes) -> None:
    with _cursor(db) as cur, cur.copy(
        "COPY api_credentials FROM STDIN (FORMAT csv, HEADER)"
    ) as copy:
        copy.write(data)


def test_relock_unlock_keeps_blank_strings_through_copy(db, make_user):
    user = make_user()
    cred = ApiCredential(
        user_id=user.id, kind="deepl", name="", endpoint_url="",
        secret_enc=encrypt_secret("s3cret"),
    )
    db.add(cred)
    db.flush()
    f = crypto.derive(PASS, crypto.new_kdf())

    locked, skipped = crypto.relock_csv(_copy_out(db), f)
    assert skipped == [] and b"s3cret" not in locked

    db.delete(cred)
    db.flush()
    _copy_in(db, crypto.unlock_csv(locked, f))
    db.expire_all()
    row = db.query(ApiCredential).one()
    assert row.name == "" and row.endpoint_url == ""
    assert decrypt_secret(row.secret_enc) == "s3cret"


def test_unreadable_credential_is_skipped(db, make_user):
    user = make_user()
    good = ApiCredential(
        user_id=user.id, kind="deepl", name="", endpoint_url="",
        secret_enc=encrypt_secret("ok"),
    )
    bad = ApiCredential(
        user_id=user.id, kind="wp", name="", endpoint_url="", secret_enc=b"garbage"
    )
    db.add_all([good, bad])
    db.flush()

    locked, skipped = crypto.relock_csv(_copy_out(db), crypto.derive(PASS, crypto.new_kdf()))

    assert skipped == [bad.id]
    assert b"garbage" not in locked


def test_wrong_passphrase_fails_verify():
    kdf = crypto.new_kdf()
    check = crypto.check_value(crypto.derive(PASS, kdf))
    with pytest.raises(WrongPassphrase) as exc:
        crypto.verify(crypto.derive("another passphrase", kdf), check)
    assert str(exc.value) == WRONG_PASSPHRASE


def test_short_passphrase_derives_and_fails_verify():
    kdf = crypto.new_kdf()
    check = crypto.check_value(crypto.derive(PASS, kdf))
    with pytest.raises(WrongPassphrase):
        crypto.verify(crypto.derive("short", kdf), check)  # restore never checks the length


@pytest.mark.parametrize("kdf", [
    {"name": "argon2", "salt": "AAAAAAAAAAAAAAAAAAAAAA==", "n": 2**15, "r": 8, "p": 1},
    {"name": "scrypt", "salt": "AAAAAAAAAAAAAAAAAAAAAA==", "n": 2**30, "r": 8, "p": 1},
    {"name": "scrypt", "salt": "AAAAAAAAAAAAAAAAAAAAAA==", "n": "32768", "r": 8, "p": 1},
    {"name": "scrypt", "salt": "not base64!", "n": 2**15, "r": 8, "p": 1},
    {"name": "scrypt", "salt": "AAAA", "n": 2**15, "r": 8, "p": 1},
    [],
])
def test_hostile_kdf_is_backup_invalid(kdf):
    with pytest.raises(BackupInvalid):
        crypto.check_kdf(kdf)


def test_manifest_round_trip_and_format_check():
    m = manifest.Manifest(
        format=1, revision="0001", created_at="2026-10-27T00:00:00+00:00",
        app_version=None, tables={"users": 1}, kdf=crypto.new_kdf(),
        check="abc", skipped_credentials=[2],
    )
    assert manifest.parse(m.to_json()) == m
    with pytest.raises(BackupInvalid, match="newer backup format"):
        manifest.parse(replace(m, format=2).to_json())


@pytest.mark.parametrize("raw", [
    b"not json",
    b"{}",
    b'{"format": 1, "revision": 5}',
    b'{"format": 1, "revision": "0001", "created_at": "x", "app_version": null,'
    b' "tables": {"users": -1}, "kdf": [], "check": "abc", "skipped_credentials": []}',
])
def test_manifest_wrong_types_are_invalid(raw):
    with pytest.raises(BackupInvalid, match="not a Translation Assistant backup"):
        manifest.parse(raw)
