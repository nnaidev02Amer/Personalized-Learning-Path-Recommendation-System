"""Schema versioning helpers built on Alembic.

Safety rules (the application never silently changes an existing database):

* an **empty** database is created from the models and stamped at the head revision;
* a database already at the head revision is used as is;
* anything else (a pre-authentication database, or an older revision) is refused at start-up with a
  clear message, and is only upgraded by the explicit command ``python -m backend.app.migrate``.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "0001"
BASELINE_TABLES = ("courses", "students", "activity_logs", "course_prerequisites", "enrollments",
                   "lessons", "quizzes", "lesson_completions", "quiz_attempts", "quiz_questions")


class SchemaOutdated(RuntimeError):
    """The database schema is not at the latest revision and must be migrated explicitly."""


def alembic_config() -> Config:
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "backend" / "migrations"))
    return cfg


def head_revision() -> str:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def current_revision(engine: Engine) -> str | None:
    if "alembic_version" not in inspect(engine).get_table_names():
        return None
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def schema_state(engine: Engine) -> str:
    """'empty' | 'current' | 'outdated' | 'legacy' (tables exist but were never versioned)."""
    tables = set(inspect(engine).get_table_names()) - {"sqlite_sequence"}
    if not tables:
        return "empty"
    rev = current_revision(engine)
    if rev is None:
        return "legacy"
    return "current" if rev == head_revision() else "outdated"


def _run(engine: Engine, fn, *args) -> None:
    cfg = alembic_config()
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        fn(cfg, *args)


def stamp(engine: Engine, revision: str = "head") -> None:
    _run(engine, command.stamp, revision)


def upgrade(engine: Engine, revision: str = "head") -> None:
    _run(engine, command.upgrade, revision)


def explain_outdated(state: str) -> str:
    return (f"The database schema needs a migration (state: {state}). Nothing was changed. "
            "Back it up, then run:  python -m backend.app.migrate   (add --dry-run to rehearse on a copy first).")
