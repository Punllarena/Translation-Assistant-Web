"""Validated, transactional restore.

Everything before the commit happens in one transaction: the app tables are dropped, the
migrations are replayed to the backup's revision, the rows are copied in, the credentials
are re-encrypted with this server's key, the sequences are reset and the migrations run on
to head. An error anywhere rolls the old server back untouched.

The file-system steps come after that commit and can still fail; they are reported as a
warning on a successful restore, never as "the server was not changed". The dictionary
files are staged before the commit (a damaged file fails the restore first) and swapped in
afterwards; ``dict.ready/`` is the marker that the database committed, so an interrupted
swap completes at the next start (``recover_dictionaries``).
"""

import csv
import io
import logging
import re
import shutil
import threading
import zipfile
from collections.abc import Callable
from pathlib import Path

import sqlalchemy as sa
from cryptography.fernet import Fernet
from psycopg import sql
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from api import accounts, dictionary
from api.backup import crypto, manifest, schema, state
from api.backup.crypto import WRONG_PASSPHRASE, WrongPassphrase
from api.backup.manifest import BackupInvalid
from api.config import get_settings
from api.db import engine

log = logging.getLogger(__name__)

GENERIC = "The restore failed; the server was not changed."
DICT_SWAP_FAILED = (
    "The database was restored, but the dictionary files could not be replaced;"
    " download EDICT2 again in Admin → Dictionary."
)
UPLOADS_LEFT = (
    "The database was restored, but some pending uploads could not be removed;"
    " delete the files under the data directory's uploads/ folder."
)
DAMAGED = "This file is not a backup or is damaged."
NEWER_REVISION = (
    "This backup comes from a newer version of Translation Assistant; upgrade this server first."
)
INCOMPLETE = "This backup is incomplete."
WRONG_VERSION = "This backup does not match its recorded version."
BUSY_DB = "The database was busy; try again when nothing is running."
SETUP_DONE = "Setup is already complete; sign in instead."
DAMAGED_DICT = "The backup's {} dictionary is damaged."

MAX_CREDENTIALS = 16 << 20
MAX_TOTAL = 32 << 30
_CREDENTIALS = "api_credentials"
MEMBER = re.compile(r"manifest\.json|tables/[a-z_0-9]+\.csv|dict/(edict|conjugations)")
STAGED, READY, OLD = "dict.restore", "dict.ready", "dict.old"


class RestoreError(Exception):
    """A failure the user should read."""


def _cap(name: str) -> int:
    if name == "manifest.json":
        return manifest.MAX_MANIFEST
    if name == f"tables/{_CREDENTIALS}.csv":
        return MAX_CREDENTIALS
    if name.startswith("dict/"):
        return dictionary.MAX_EDICT_BYTES
    return MAX_TOTAL


class BackupReader:
    """An open, entirely validated backup. ``rows`` streams one table's CSV member."""

    def __init__(self, path: Path, zipf: zipfile.ZipFile, m: manifest.Manifest, f: Fernet) -> None:
        self.path, self.manifest, self.fernet = path, m, f
        self._zip = zipf
        self._names = frozenset(zipf.namelist())

    @classmethod
    def open(cls, path: Path, passphrase: str) -> "BackupReader":
        """Validate the whole file before anything is touched: raises BackupInvalid or
        WrongPassphrase, so a restore never starts on a file it cannot load."""
        try:
            zipf = zipfile.ZipFile(path)
        except (zipfile.BadZipFile, OSError):
            raise BackupInvalid(DAMAGED) from None
        try:
            return cls._validated(path, zipf, passphrase)
        except BaseException:
            zipf.close()
            raise

    @classmethod
    def _validated(cls, path, zipf, passphrase) -> "BackupReader":
        infos = {info.filename: info for info in zipf.infolist()}
        for name, info in infos.items():
            if MEMBER.fullmatch(name) is None or info.file_size > _cap(name):
                raise BackupInvalid(DAMAGED)
        if sum(info.file_size for info in infos.values()) > MAX_TOTAL:
            raise BackupInvalid(DAMAGED)
        info = infos.get("manifest.json")
        if info is None:
            raise BackupInvalid(manifest.NOT_A_BACKUP)
        with zipf.open(info) as handle:
            raw = handle.read(manifest.MAX_MANIFEST + 1)
        if len(raw) > manifest.MAX_MANIFEST:
            raise BackupInvalid(DAMAGED)
        m = manifest.parse(raw)
        if not schema.is_known(m.revision):
            raise BackupInvalid(NEWER_REVISION)
        f = crypto.derive(passphrase, m.kdf)
        crypto.verify(f, m.check)
        tables = {
            name.removeprefix("tables/").removesuffix(".csv")
            for name in infos
            if name.startswith("tables/")
        }
        if tables != set(m.tables):
            raise BackupInvalid(INCOMPLETE)
        return cls(path, zipf, m, f)

    def rows(self, table: str):
        return self._zip.open(f"tables/{table}.csv")

    def dict_kinds(self) -> list[str]:
        return [kind for kind in dictionary.FILENAMES if f"dict/{kind}" in self._names]

    def read_dict(self, kind: str) -> bytes:
        return self._zip.read(f"dict/{kind}")

    def close(self) -> None:
        self._zip.close()


def _root() -> Path:
    return Path(get_settings().data_dir)


def stage_dictionaries(reader: BackupReader) -> Path | None:
    """Validate the backup's dictionaries into a fresh dict.restore/ (never the live dict/).

    An empty directory still stages when a dictionary lives in the data dir, so a backup
    without EDICT2 removes the old server's file. None: both come from the environment.
    """
    members = reader.dict_kinds()
    in_data_dir = [k for k in dictionary.FILENAMES if dictionary.resolve(k)[1] == "data_dir"]
    if not members and not in_data_dir:
        return None
    staged = _root() / STAGED
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    for kind in members:
        data = reader.read_dict(kind)
        try:
            dictionary.validate(kind, data)
        except ValueError as exc:
            raise BackupInvalid(DAMAGED_DICT.format(kind)) from exc
        (staged / dictionary.FILENAMES[kind]).write_bytes(data)
    return staged


def mark_committed(staged: Path | None) -> None:
    """The database committed: this rename is the only record of it."""
    if staged is not None:
        staged.rename(_root() / READY)


def swap_dictionaries() -> None:
    """Replace dict/ with dict.ready/. An OSError leaves dict.ready/ for the next start."""
    root = _root()
    ready, old, current = root / READY, root / OLD, root / "dict"
    if not ready.exists():
        return
    if old.exists():
        shutil.rmtree(old)
    if current.exists():
        current.rename(old)
    ready.rename(current)
    dictionary._drop_cached()
    try:
        shutil.rmtree(old)  # best effort: a leftover is removed at the next start
    except OSError:
        log.warning("could not remove %s", old, exc_info=True)


def recover_dictionaries() -> None:
    """At startup: leave exactly one dictionary directory, completing an interrupted swap."""
    root = _root()
    current, old = root / "dict", root / OLD
    shutil.rmtree(root / STAGED, ignore_errors=True)  # never committed
    if (root / READY).exists():
        try:
            swap_dictionaries()
        except OSError:
            log.exception("completing the dictionary swap failed")
    if current.exists():
        shutil.rmtree(old, ignore_errors=True)
    elif old.exists():
        old.rename(current)  # the only copy left: put it back


def _check_header(reader: BackupReader, table: sa.Table) -> None:
    with reader.rows(table.name) as member:
        line = member.readline()
    header = next(csv.reader(io.StringIO(line.decode("utf-8"))), [])
    if header != [column.name for column in table.columns]:
        raise BackupInvalid(WRONG_VERSION)


def _load(conn: Connection, reader: BackupReader, table: sa.Table, cur) -> int:
    name = table.name
    columns = [column.name for column in table.columns]
    copy_sql = sql.SQL("COPY {} ({}) FROM STDIN (FORMAT csv, HEADER)").format(
        sql.Identifier(name), sql.SQL(", ").join(sql.Identifier(c) for c in columns)
    )
    with cur.copy(copy_sql) as copy, reader.rows(name) as member:
        if name == _CREDENTIALS:
            copy.write(crypto.unlock_csv(member.read(), reader.fernet))
        else:
            while chunk := member.read(1 << 20):
                copy.write(chunk)
    return conn.scalar(sa.text(f'SELECT count(*) FROM "{name}"'))


def apply(
    conn: Connection,
    reader: BackupReader,
    *,
    from_setup: bool,
    progress: Callable[[int, int, str], None],
) -> None:
    """Replace every app table with the backup's, in the caller's transaction."""
    m = reader.manifest
    conn.execute(sa.text("SET LOCAL lock_timeout = '30s'"))
    if from_setup:
        conn.execute(sa.select(sa.func.pg_advisory_xact_lock(accounts.SETUP_LOCK)))
        if conn.scalar(sa.text("SELECT 1 FROM users LIMIT 1")) is not None:
            raise RestoreError(SETUP_DONE)
    schema.drop_app_tables(conn)
    schema.upgrade(conn, m.revision)
    tables = schema.reflect_app_tables(conn)
    live = {table.name for table in tables} - {"sessions"}
    if live != set(m.tables):
        raise BackupInvalid(INCOMPLETE)
    total, done = sum(m.tables.values()), 0
    with conn.connection.driver_connection.cursor() as cur:
        for table in tables:
            if table.name == "sessions":
                continue
            _check_header(reader, table)
            loaded = _load(conn, reader, table, cur)
            if loaded != m.tables[table.name]:
                raise BackupInvalid(INCOMPLETE)
            done += loaded
            progress(done, total, table.name)
    schema.reset_sequences(conn)
    schema.upgrade(conn, schema.head())


def clear_uploads(keep: Path) -> bool:
    """Delete everything under uploads/ except ``keep``; False when something is left."""
    left = False
    for path in sorted((_root() / "uploads").rglob("*")):
        if path == keep or path.is_dir():
            continue
        try:
            path.unlink()
        except OSError:
            log.warning("could not delete %s", path, exc_info=True)
            left = True
    return not left


def _discard(staged: Path | None) -> None:
    if staged is not None:
        shutil.rmtree(staged, ignore_errors=True)


def _sqlstate(exc: OperationalError) -> str | None:
    return getattr(exc.orig, "sqlstate", None)


def _after_commit(reader: BackupReader, staged: Path | None) -> list[str]:
    """The database already committed: each failure here is a warning, never a failure."""
    warnings: list[str] = []
    try:
        mark_committed(staged)
        swap_dictionaries()
    except OSError:
        log.exception("replacing the dictionary files failed")
        warnings.append(DICT_SWAP_FAILED)
    try:
        cleared = clear_uploads(keep=reader.path)
    except OSError:
        log.exception("clearing the uploads failed")
        cleared = False
    if not cleared:
        warnings.append(UPLOADS_LEFT)
    engine.dispose()
    return warnings


def run(reader: BackupReader, from_setup: bool) -> None:
    """The restore thread. Nothing that happens after the commit reaches the pre-commit
    handlers: a committed restore may only be reported as done."""
    staged: Path | None = None
    try:
        try:
            staged = stage_dictionaries(reader)
            with engine.begin() as conn:
                apply(conn, reader, from_setup=from_setup, progress=state.progress)
        except (RestoreError, BackupInvalid) as exc:
            _discard(staged)
            state.fail(str(exc))
            return
        except WrongPassphrase:
            _discard(staged)
            state.fail(WRONG_PASSPHRASE)
            return
        except OperationalError as exc:
            _discard(staged)
            if _sqlstate(exc) == "55P03":  # lock_not_available: lock_timeout ran out
                state.fail(BUSY_DB)
            else:
                log.exception("restore failed")
                state.fail(GENERIC)
            return
        except Exception:
            _discard(staged)
            log.exception("restore failed")
            state.fail(GENERIC)
            return
        state.finish(" ".join(_after_commit(reader, staged)) or None)
    finally:
        reader.close()
        try:
            reader.path.unlink(missing_ok=True)
        except OSError:
            log.warning("could not delete the restore upload %s", reader.path, exc_info=True)


def start(reader: BackupReader, from_setup: bool) -> None:
    """Hand the restore to its own thread (it replaces the jobs table it would report to).

    The caller has already won ``state.try_begin``.
    """
    threading.Thread(target=run, args=(reader, from_setup), name="restore", daemon=True).start()
