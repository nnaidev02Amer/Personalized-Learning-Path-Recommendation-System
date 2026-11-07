"""SQLAlchemy engine/session setup."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    kwargs = {}
    if url.startswith("sqlite"):
        # FastAPI may use the session from a worker thread.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
    return engine


class Database:
    """Holds the engine and session factory for one application instance."""

    def __init__(self, url: str):
        self.engine = make_engine(url)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)

    def create_all(self) -> None:
        """Create the tables of a *new* database and stamp it at the current schema revision.

        An existing database is never altered here: if it is not already current this raises
        ``SchemaOutdated`` (migrate it explicitly with ``python -m backend.app.migrate``).
        """
        from backend.app import migrations, models  # noqa: F401  (registers tables)
        state = migrations.schema_state(self.engine)
        if state == "empty":
            Base.metadata.create_all(self.engine)
            migrations.stamp(self.engine)
        elif state != "current":
            raise migrations.SchemaOutdated(migrations.explain_outdated(state))

    def drop_all(self) -> None:
        from sqlalchemy import text
        from backend.app import models  # noqa: F401
        Base.metadata.drop_all(self.engine)
        with self.engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS alembic_version"))

    def session(self) -> Iterator[Session]:
        db = self.SessionLocal()
        try:
            yield db
        finally:
            db.close()
