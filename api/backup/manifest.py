"""The backup's manifest: what the file holds, and the revision it holds it for."""

import json
from dataclasses import asdict, dataclass

from api.backup import crypto

FORMAT_VERSION = 1
MAX_MANIFEST = 1 << 20
NOT_A_BACKUP = "This is not a Translation Assistant backup."
NEWER_FORMAT = "This backup was made by a newer backup format; upgrade this server first."


class BackupInvalid(Exception):
    """The file is not a usable backup; the message is shown to the user."""


@dataclass
class Manifest:
    format: int
    revision: str
    created_at: str
    app_version: str | None
    tables: dict[str, int]
    kdf: dict
    check: str
    skipped_credentials: list[int]

    def to_json(self) -> bytes:
        return json.dumps(asdict(self)).encode("utf-8")


def _int(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError
    return value


def _str(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError
    return value


def _counts(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        raise TypeError
    counts: dict[str, int] = {}
    for name, n in value.items():
        if not isinstance(name, str) or _int(n) < 0:
            raise TypeError
        counts[name] = n
    return counts


def _parse(raw: bytes) -> Manifest:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise BackupInvalid(NOT_A_BACKUP) from None
    if not isinstance(data, dict):
        raise BackupInvalid(NOT_A_BACKUP)
    try:
        app_version = data["app_version"]
        kdf = data["kdf"]
        skipped = data["skipped_credentials"]
        if not isinstance(kdf, dict) or not isinstance(skipped, list):
            raise TypeError
        return Manifest(
            format=_int(data["format"]),
            revision=_str(data["revision"]),
            created_at=_str(data["created_at"]),
            app_version=None if app_version is None else _str(app_version),
            tables=_counts(data["tables"]),
            kdf=kdf,
            check=_str(data["check"]),
            skipped_credentials=[_int(i) for i in skipped],
        )
    except (KeyError, TypeError):
        raise BackupInvalid(NOT_A_BACKUP) from None


def parse(raw: bytes) -> Manifest:
    """Read a manifest, refusing anything this server could not load safely."""
    m = _parse(raw)
    if m.format != FORMAT_VERSION:
        raise BackupInvalid(NEWER_FORMAT)
    crypto.check_kdf(m.kdf)
    return m
