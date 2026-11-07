"""Alembic environment. The URL comes from the config object (set by the migrate CLI / tests) or,
failing that, from the application settings (DATABASE_URL, default data/app.db)."""

from alembic import context
from sqlalchemy import create_engine

from backend.app.config import get_settings

config = context.config


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:                       # caller supplied a connection (tests, CLI)
        context.configure(connection=connection, target_metadata=None, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
        return
    engine = create_engine(_url())
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=None, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
