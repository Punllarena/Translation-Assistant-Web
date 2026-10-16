"""EDICT2 and Conjugations files kept under TA_DATA_DIR (spec §5). An explicit
TA_EDICT_PATH / TA_CONJUGATIONS_PATH wins, so env-configured installs are unchanged."""

import os
import tempfile
import zlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from api.config import get_settings

Kind = Literal["edict", "conjugations"]
FILENAMES = {"edict": "edict2", "conjugations": "conjugations.txt"}
ENV_FIELDS = {"edict": "edict_path", "conjugations": "conjugations_path"}
MIN_EDICT_ENTRIES = 1000  # the real file has ~190k; this only rejects the wrong file
MAX_EDICT_BYTES = 128 * 1024 * 1024
MAX_UPLOAD = 64 * 1024 * 1024


def dict_dir() -> Path:
    return Path(get_settings().data_dir) / "dict"


def env_path(kind: Kind) -> str:
    return getattr(get_settings(), ENV_FIELDS[kind])


def resolve(kind: Kind) -> tuple[str, str | None]:
    if p := env_path(kind):
        return p, "env"
    p = dict_dir() / FILENAMES[kind]
    return (str(p), "data_dir") if p.is_file() else ("", None)


def path(kind: Kind) -> str:
    return resolve(kind)[0]


def gunzip_capped(data: bytes) -> bytes:
    """Plain bytes pass through; gzip is unpacked, refusing more than MAX_EDICT_BYTES."""
    if not data.startswith(b"\x1f\x8b"):
        out, more = data, False
    else:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        try:
            out = d.decompress(data, MAX_EDICT_BYTES + 1)
        except zlib.error as exc:
            raise ValueError(f"the file is not valid gzip: {exc}") from exc
        more = bool(d.unconsumed_tail)
        if not more and len(out) <= MAX_EDICT_BYTES and not d.eof:
            raise ValueError("the file is not valid gzip: truncated")
    if more or len(out) > MAX_EDICT_BYTES:
        raise ValueError(f"the dictionary is larger than {MAX_EDICT_BYTES >> 20} MiB unpacked")
    return out


def _count(kind: Kind, p: Path) -> int:
    from api.mt import jparser  # jparser resolves its paths through this module

    if kind == "edict":
        n = len(jparser._read_index(str(p)) or {})
        if n < MIN_EDICT_ENTRIES:
            raise ValueError("this does not look like EDICT2: too few dictionary entries")
        return n
    try:
        n = len(jparser._load_conj_rules(str(p)))
    except (ValueError, KeyError, TypeError) as exc:  # json and unicode errors are ValueError
        raise ValueError(f"this is not a Conjugations file: {exc}") from exc
    if n == 0:
        raise ValueError("this is not a Conjugations file: it has no rules")
    return n


def _drop_cached() -> None:
    """Free a replaced or removed index now instead of when the LRU evicts it."""
    from api.mt import jparser

    jparser._load_index_locked.cache_clear()
    jparser._load_rules_cached.cache_clear()


def install(kind: Kind, data: bytes) -> int:
    """Validate, then atomically replace the data-dir file. Returns the entry/rule count."""
    d = dict_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=FILENAMES[kind] + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        n = _count(kind, Path(tmp))
        os.replace(tmp, d / FILENAMES[kind])
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    _drop_cached()
    return n


def status(kind: Kind) -> dict:
    from api.mt import jparser

    p, source = resolve(kind)
    try:
        st = os.stat(p) if p else None
    except OSError:
        st = None
    if st is None:
        return {"present": False, "source": source, "size": None, "updated_at": None,
                "entries": None}
    entries = (len(jparser.load_index(p) or {}) if kind == "edict"
               else len(jparser.load_rules(p)))
    return {"present": True, "source": source, "size": st.st_size,
            "updated_at": datetime.fromtimestamp(st.st_mtime, UTC), "entries": entries}


def remove(kind: Kind) -> None:
    (dict_dir() / FILENAMES[kind]).unlink(missing_ok=True)
    _drop_cached()
