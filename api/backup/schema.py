"""Schema helpers shared by export and restore.

The restore replays the migrations on its own connection, so the empty schema it migrates
and the rows it copies land in one transaction (``migrations/env.py`` reads the connection
from ``config.attributes``). Everything here works on the reflected schema, never on
``Base``, so a backup made at an old revision can be exported and loaded too.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util import CommandError
from sqlalchemy import MetaData, inspect, text
from sqlalchemy.engine import Connection

from api.db import Base

ROOT = Path(__file__).resolve().parents[2]
# A table an old revision created and a later one dropped. It is an app table all the same:
# the restore drops it, so a stray one left by an interrupted migration never blocks a load.
RETIRED_TABLES = frozenset({"profiles"})
VERSION_TABLE = "alembic_version"


def alembic_config(conn: Connection | None = None) -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    if conn is not None:
        cfg.attributes["connection"] = conn
    return cfg


def _script() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def head() -> str:
    return _script().get_current_head()


def is_known(rev: str) -> bool:
    """True when this server's migrations include the revision."""
    try:
        return _script().get_revision(rev) is not None
    except CommandError:  # ResolutionError is one
        return False


def current_revision(conn: Connection) -> str | None:
    if VERSION_TABLE not in inspect(conn).get_table_names():
        return None
    return conn.scalar(text(f"SELECT version_num FROM {VERSION_TABLE}"))


def upgrade(conn: Connection, rev: str) -> None:
    """Run the migrations up to ``rev`` on the caller's connection (no commit)."""
    command.upgrade(alembic_config(conn), rev)


def app_table_names() -> frozenset[str]:
    return frozenset(Base.metadata.tables) | RETIRED_TABLES


def drop_app_tables(conn: Connection) -> None:
    """Drop every app table and the version row, leaving any stray table alone."""
    for name in sorted(app_table_names()) + [VERSION_TABLE]:
        conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))


def reflect_app_tables(conn: Connection) -> list:
    """The live app tables, in dependency order (``alembic_version`` is not one)."""
    wanted = sorted(app_table_names() & set(inspect(conn).get_table_names()))
    metadata = MetaData()
    metadata.reflect(bind=conn, only=wanted)
    return [t for t in metadata.sorted_tables if t.name in app_table_names()]


_SEQUENCES = text(
    "SELECT table_name, column_name,"
    " pg_get_serial_sequence(quote_ident(table_name), column_name)"
    " FROM information_schema.columns WHERE table_schema = current_schema()"
)


def reset_sequences(conn: Connection) -> None:
    """Point every serial sequence past its table's max id; an empty table starts at 1."""
    for table, column, seq in conn.execute(_SEQUENCES).all():
        if seq is None:
            continue
        top = conn.scalar(text(f'SELECT max("{column}") FROM "{table}"'))
        conn.execute(
            text("SELECT setval(:seq, :value, :called)"),
            {"seq": seq, "value": 1 if top is None else top, "called": top is not None},
        )
