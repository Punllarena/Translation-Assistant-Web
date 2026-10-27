"""Snapshot → zip: one COPY CSV member per app table, the data-dir dictionary files, then
the manifest.

It works from the reflected schema, never ``Base``, so it also exports an old revision's
tables (a backup built by the tests, and one made before an upgrade). Unfinished jobs are
left out and every reference to one becomes NULL, which is why the rows come from a query
rather than the bare table.
"""

import importlib.metadata
import queue
import shutil
import threading
import zipfile
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import BinaryIO

from cryptography.fernet import Fernet
from psycopg import sql
from sqlalchemy import Connection, Table

from api import dictionary, jobs
from api.backup import crypto, manifest, schema
from api.db import engine

EXCLUDED = frozenset({"sessions"})
CHUNK = 1 << 20
TERMINAL_IDS = sql.SQL(", ").join(sql.Literal(state) for state in sorted(jobs.TERMINAL))


def _references_jobs(column) -> bool:
    return any(fk.column.table.name == "jobs" for fk in column.foreign_keys)


def table_query(table: Table) -> sql.Composed:
    """The table's rows as the backup keeps them: no unfinished job, no link to one."""
    columns = []
    for column in table.columns:
        ident = sql.Identifier(column.name)
        if _references_jobs(column):
            columns.append(
                sql.SQL("CASE WHEN {c} IN (SELECT id FROM jobs WHERE state IN ({s}))"
                        " THEN {c} END AS {c}").format(c=ident, s=TERMINAL_IDS)
            )
        else:
            columns.append(ident)
    query = sql.SQL("SELECT {} FROM {}").format(
        sql.SQL(", ").join(columns), sql.Identifier(table.name)
    )
    if table.name == "jobs":
        query = sql.SQL("{} WHERE {} IN ({})").format(
            query, sql.Identifier("state"), TERMINAL_IDS
        )
    return query


def _app_version() -> str | None:
    try:
        return importlib.metadata.version("ta-web")
    except importlib.metadata.PackageNotFoundError:
        return None


def _copy(cur, zf: zipfile.ZipFile, table: Table, f: Fernet) -> tuple[int, list[int]]:
    """Write one table's member; returns the row count and the dropped credential ids."""
    query = table_query(table)
    cur.execute(sql.SQL("SELECT count(*) FROM ({}) q").format(query))
    count = cur.fetchone()[0]
    skipped: list[int] = []
    with zf.open(f"tables/{table.name}.csv", "w", force_zip64=True) as member:
        with cur.copy(
            sql.SQL("COPY ({}) TO STDOUT (FORMAT csv, HEADER)").format(query)
        ) as copy:
            if table.name == "api_credentials":
                data, skipped = crypto.relock_csv(b"".join(copy), f)
                count -= len(skipped)
                member.write(data)
            else:
                for chunk in copy:
                    member.write(chunk)
    return count, skipped


def write(conn: Connection, out: BinaryIO, f: Fernet, kdf: dict) -> manifest.Manifest:
    """The whole server into ``out``. ``f`` locks the credentials; ``kdf`` describes it."""
    counts: dict[str, int] = {}
    skipped: list[int] = []
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        with conn.connection.driver_connection.cursor() as cur:
            for table in schema.reflect_app_tables(conn):
                if table.name in EXCLUDED:
                    continue
                count, dropped = _copy(cur, zf, table, f)
                counts[table.name], skipped = count, skipped + dropped
        for kind in dictionary.FILENAMES:
            path, source = dictionary.resolve(kind)
            if source != "data_dir":
                continue
            with zf.open(f"dict/{kind}", "w", force_zip64=True) as member, open(path, "rb") as src:
                shutil.copyfileobj(src, member)
        m = manifest.Manifest(
            format=manifest.FORMAT_VERSION,
            revision=schema.current_revision(conn),
            created_at=datetime.now(UTC).isoformat(),
            app_version=_app_version(),
            tables=counts,
            kdf=kdf,
            check=crypto.check_value(f),
            skipped_credentials=skipped,
        )
        zf.writestr("manifest.json", m.to_json())
    return m


def filename(today: date) -> str:
    return f"ta-backup-{today.isoformat()}.zip"


class _Sink:
    """A zip target that hands out ~1 MiB chunks as they are written, never seeking."""

    def __init__(self, emit, size: int = CHUNK) -> None:
        self._emit, self._size = emit, size
        self._pending = bytearray()

    def write(self, data: bytes) -> int:
        self._pending += data
        while len(self._pending) >= self._size:
            self._emit(bytes(self._pending[: self._size]))
            del self._pending[: self._size]
        return len(data)

    def flush(self) -> None:
        if self._pending:
            self._emit(bytes(self._pending))
            self._pending.clear()


def stream(f: Fernet, kdf: dict) -> Iterator[bytes]:
    """The zip as buffered chunks, built in its own REPEATABLE READ, read-only transaction
    so the file is one consistent snapshot while people keep working."""
    chunks: queue.Queue[bytes | BaseException | None] = queue.Queue()

    def run() -> None:
        try:
            with engine.connect().execution_options(
                isolation_level="REPEATABLE READ", postgresql_readonly=True
            ) as conn:
                sink = _Sink(chunks.put)
                write(conn, sink, f, kdf)
                sink.flush()
        except BaseException as exc:  # a broken export must reach the client, not only a log
            chunks.put(exc)
        finally:
            chunks.put(None)

    thread = threading.Thread(target=run, name="backup-export", daemon=True)
    thread.start()
    try:
        while (item := chunks.get()) is not None:
            if isinstance(item, BaseException):
                raise item
            yield item
    finally:
        thread.join()
