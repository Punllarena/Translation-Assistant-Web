"""Alembic on a passed connection, and the schema helpers export/restore use."""

from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from api.backup import schema
from api.db import Base


def test_drop_then_upgrade_to_head_rebuilds_every_table(db):
    conn = db.connection()
    schema.drop_app_tables(conn)
    assert "users" not in inspect(conn).get_table_names()
    schema.upgrade(conn, schema.head())
    assert {t.name for t in Base.metadata.sorted_tables} <= set(inspect(conn).get_table_names())
    assert schema.current_revision(conn) == schema.head()


def test_upgrade_to_an_older_revision_stops_there(db):
    conn = db.connection()
    schema.drop_app_tables(conn)
    schema.upgrade(conn, "fc7f71015e51")
    assert schema.current_revision(conn) == "fc7f71015e51"
    assert "volume_covers" not in {t.name for t in schema.reflect_app_tables(conn)}


def test_every_table_any_revision_creates_is_an_app_table(db):
    """A migration that retires a table without listing it in RETIRED_TABLES is caught here."""
    conn = db.connection()
    schema.drop_app_tables(conn)
    script = ScriptDirectory.from_config(schema.alembic_config())
    for rev in reversed(list(script.walk_revisions())):  # base -> head
        schema.upgrade(conn, rev.revision)
        live = set(inspect(conn).get_table_names()) - {schema.VERSION_TABLE}
        assert live <= set(schema.app_table_names()), rev.revision


def test_stray_tables_are_ignored(db):
    conn = db.connection()
    conn.execute(text("CREATE TABLE stray_notes (id int)"))
    assert "stray_notes" not in {t.name for t in schema.reflect_app_tables(conn)}
    schema.drop_app_tables(conn)
    assert "stray_notes" in inspect(conn).get_table_names()


def test_unknown_revision_is_not_known():
    assert schema.is_known(schema.head())
    assert not schema.is_known("ffffffffffff")


def test_reset_sequences_continues_after_max(db, make_user):
    u = make_user()
    conn = db.connection()
    conn.execute(text("UPDATE users SET id = id + 1000 WHERE id = :i"), {"i": u.id})
    schema.reset_sequences(conn)
    assert make_user(email="b@example.com").id == u.id + 1001
