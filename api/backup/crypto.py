"""The backup passphrase: a scrypt KDF whose parameters are strictly validated, a check
value, and the NULL-faithful rewrite of ``api_credentials`` rows.

Only ``api_credentials.secret_enc`` is locked; everything else in the file is as it is. The
passphrase lives in the request that uses it, never in a job row, a log or the status route.
"""

import base64
import binascii
import csv
import io
import secrets

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from api.backup import copycsv
from api.security import decrypt_secret, encrypt_secret

KDF_N, KDF_R, KDF_P = 2**15, 8, 1
SALT_BYTES = 16
CHECK = b"ta-web backup v1"
WRONG_PASSPHRASE = "The passphrase is wrong."
KDF_FIELDS = frozenset({"name", "salt", "n", "r", "p"})


class WrongPassphrase(Exception):
    """Every raise passes ``WRONG_PASSPHRASE``, so ``str(exc)`` is never empty."""


def new_kdf() -> dict:
    salt = base64.b64encode(secrets.token_bytes(SALT_BYTES)).decode("ascii")
    return {"name": "scrypt", "salt": salt, "n": KDF_N, "r": KDF_R, "p": KDF_P}


def check_kdf(kdf: object) -> dict:
    """The one KDF shape this server writes; anything else would ask for unbounded work."""
    from api.backup.manifest import BackupInvalid  # manifest imports this module

    invalid = BackupInvalid("This backup's key settings are not valid.")
    if not isinstance(kdf, dict) or set(kdf) != KDF_FIELDS:
        raise invalid
    if kdf["name"] != "scrypt" or kdf["n"] != KDF_N or kdf["r"] != KDF_R or kdf["p"] != KDF_P:
        raise invalid
    salt = kdf["salt"]
    try:
        if not isinstance(salt, str) or len(base64.b64decode(salt, validate=True)) != SALT_BYTES:
            raise invalid
    except (binascii.Error, ValueError):
        raise invalid from None
    return kdf


def derive(passphrase: str, kdf: dict) -> Fernet:
    """The key for a backup's passphrase. It never checks the passphrase's length: a short
    one simply fails ``verify``, so raising MIN_PASSWORD later cannot lock out old backups."""
    check_kdf(kdf)
    salt = base64.b64decode(kdf["salt"])
    key = Scrypt(salt=salt, length=32, n=KDF_N, r=KDF_R, p=KDF_P).derive(passphrase.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def check_value(f: Fernet) -> str:
    return f.encrypt(CHECK).decode("ascii")


def verify(f: Fernet, check: str) -> None:
    """Raise WrongPassphrase unless ``check`` was encrypted with this key."""
    try:
        if f.decrypt(check.encode("ascii")) == CHECK:
            return
    except (InvalidToken, UnicodeEncodeError):
        pass
    raise WrongPassphrase(WRONG_PASSPHRASE)


def _split(data: bytes) -> tuple[list[str], list[dict[str, str | None]]]:
    """Read COPY's CSV so ``""`` stays an empty string and NULL is None."""
    table = copycsv.rows(data.decode("utf-8"))
    fields = [f or "" for f in table[0]] if table else []
    if "id" not in fields or "secret_enc" not in fields:
        raise ValueError("not an api_credentials table")
    return fields, [dict(zip(fields, r, strict=True)) for r in table[1:]]


def _join(fields: list[str], rows: list[dict[str, str | None]]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=fields, quoting=csv.QUOTE_NOTNULL, lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def _unhex(value: str | None) -> bytes | None:
    if value is None:
        return None
    return bytes.fromhex(value[2:] if value.startswith("\\x") else value)


def _hex(blob: bytes) -> str:
    return f"\\x{blob.hex()}"


def relock_csv(data: bytes, f: Fernet) -> tuple[bytes, list[int]]:
    """Lock each secret with the backup passphrase. A row this server's key cannot read is
    left out and its id returned, so the manifest can list it as skipped."""
    fields, rows = _split(data)
    kept: list[dict[str, str | None]] = []
    skipped: list[int] = []
    for row in rows:
        try:
            plain = decrypt_secret(_unhex(row["secret_enc"]) or b"")
        except ValueError:
            skipped.append(int(row["id"] or 0))
            continue
        row["secret_enc"] = _hex(f.encrypt(plain.encode("utf-8")))
        kept.append(row)
    return _join(fields, kept), skipped


def unlock_csv(data: bytes, f: Fernet) -> bytes:
    """Re-encrypt each secret with this server's key (WrongPassphrase on a bad token)."""
    fields, rows = _split(data)
    for row in rows:
        blob = _unhex(row["secret_enc"])
        if blob is None:
            continue
        try:
            plain = f.decrypt(blob).decode("utf-8")
        except InvalidToken:
            raise WrongPassphrase(WRONG_PASSPHRASE) from None
        row["secret_enc"] = _hex(encrypt_secret(plain))
    return _join(fields, rows)
