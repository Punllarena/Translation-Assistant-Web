from alembic import context
from sqlalchemy import create_engine

import api.models  # noqa: F401  — registers every mapper with Base.metadata
from api.config import get_settings
from api.db import Base

target_metadata = Base.metadata


def _configure(connection) -> None:
    context.configure(
        connection=connection, target_metadata=target_metadata, compare_type=True
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # The restore passes its own connection (api/backup/schema.py), so the migrations run in
    # the restore's transaction and are rolled back with it.
    connection = context.config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    engine = create_engine(get_settings().database_url, future=True)
    with engine.connect() as connection:
        _configure(connection)


if context.is_offline_mode():
    context.configure(url=get_settings().database_url, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
else:
    run_migrations_online()
