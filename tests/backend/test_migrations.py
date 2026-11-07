"""Alembic migrations: baseline stamping, additive upgrade, data preservation, start-up safety."""

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from backend.app import migrate, migrations
from backend.app.config import Settings
from backend.app.database import Database
from backend.app.main import create_app

BASELINE_FILE = Path(migrations.ROOT, "backend", "migrations", "versions", "0001_baseline.py")


def baseline_ddl():
    spec = importlib.util.spec_from_file_location("baseline_0001", BASELINE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.DDL


def make_legacy_db(path: Path) -> dict:
    """A populated database exactly as it was before authentication existed (no alembic_version)."""
    con = sqlite3.connect(path)
    for statement in baseline_ddl():
        con.execute(statement)
    con.executemany("INSERT INTO students VALUES (?,?,?,?,?,?,?,?,?)", [
        (1, "Ada", "ada@example.edu", 22, "Visual", "Videos", 60.0, 1, "2026-01-01 00:00:00"),
        (2, "Bo", "bo@example.edu", 30, None, "Articles", 45.0, 0, "2026-01-02 00:00:00")])
    con.execute("INSERT INTO courses VALUES (1,'PY101','Python','d','Programming','Beginner',1,'Videos',5.0,'[\"loops\"]')")
    con.execute("INSERT INTO lessons VALUES (1,1,1,'Intro',10)")
    con.execute("INSERT INTO enrollments VALUES (1,1,1,'active',NULL,'2026-01-03 00:00:00',NULL)")
    con.execute("INSERT INTO activity_logs VALUES (1,1,1,'2026-01-03',30.0,'study')")
    con.commit()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in migrations.BASELINE_TABLES}
    con.close()
    return counts


def columns(engine):
    insp = inspect(engine)
    return {t: sorted((c["name"], str(c["type"]).split("(")[0]) for c in insp.get_columns(t))
            for t in insp.get_table_names() if t != "alembic_version"}


def test_fresh_database_is_created_and_stamped_at_head(tmp_path):
    db = Database(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    db.create_all()
    assert migrations.schema_state(db.engine) == "current"
    assert migrations.current_revision(db.engine) == migrations.head_revision() == "0004"
    db.create_all()                                  # idempotent
    db.engine.dispose()


def test_migrated_schema_matches_the_orm_models(tmp_path):
    """Guards against drift between the models and the migrations."""
    legacy = tmp_path / "legacy.db"
    make_legacy_db(legacy)
    assert migrate.run_migration(f"sqlite:///{legacy.as_posix()}")["ok"]
    fresh = Database(f"sqlite:///{(tmp_path / 'fresh.db').as_posix()}")
    fresh.create_all()
    migrated = create_engine(f"sqlite:///{legacy.as_posix()}")
    assert columns(migrated) == columns(fresh.engine)
    migrated.dispose()
    fresh.engine.dispose()


def test_legacy_database_migrates_without_losing_a_row(tmp_path):
    path = tmp_path / "legacy.db"
    counts = make_legacy_db(path)
    url = f"sqlite:///{path.as_posix()}"
    engine = create_engine(url)
    assert migrations.schema_state(engine) == "legacy"
    engine.dispose()

    report = migrate.run_migration(url)
    assert report["ok"] and report["state_before"] == "legacy" and report["state_after"] == "current"
    assert report["rows_before"] == counts == {t: report["rows_after"][t] for t in counts}
    assert {"users", "auth_sessions", "recommendation_history"} <= set(report["rows_after"])
    assert report["health_after"] == {"integrity_check": "ok", "foreign_key_violations": 0}

    con = sqlite3.connect(path)
    assert con.execute("SELECT is_active FROM courses").fetchall() == [(1,)]       # existing course stays active
    assert con.execute("SELECT name, email FROM students ORDER BY id").fetchall() == [
        ("Ada", "ada@example.edu"), ("Bo", "bo@example.edu")]
    assert con.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0           # no accounts invented
    con.close()

    again = migrate.run_migration(url)                                              # second run is a no-op
    assert again["changed"] is False


def test_downgrade_of_the_baseline_is_refused():
    spec = importlib.util.spec_from_file_location("baseline_0001", BASELINE_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(RuntimeError):
        module.downgrade()


def test_create_all_never_alters_an_existing_legacy_database(tmp_path):
    path = tmp_path / "legacy.db"
    counts = make_legacy_db(path)
    db = Database(f"sqlite:///{path.as_posix()}")
    with pytest.raises(migrations.SchemaOutdated):
        db.create_all()
    db.engine.dispose()
    con = sqlite3.connect(path)
    names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "users" not in names and "alembic_version" not in names                  # untouched
    assert {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in migrations.BASELINE_TABLES} == counts
    con.close()


def test_app_refuses_to_start_on_an_unmigrated_database_and_leaves_it_alone(tmp_path):
    path = tmp_path / "legacy.db"
    make_legacy_db(path)
    before = path.read_bytes()
    settings = Settings(database_url=f"sqlite:///{path.as_posix()}", seed_on_startup=False,
                        ml_train_on_startup=False)
    with pytest.raises(migrations.SchemaOutdated):
        with TestClient(create_app(settings)):
            pass
    assert path.read_bytes() == before


def test_cli_backs_up_first_and_never_overwrites(tmp_path, capsys):
    path = tmp_path / "legacy.db"
    counts = make_legacy_db(path)
    url = f"sqlite:///{path.as_posix()}"
    assert migrate.main(["--url", url, "--dry-run"]) == 0
    con = sqlite3.connect(path)
    assert "users" not in {r[0] for r in con.execute("SELECT name FROM sqlite_master")}   # dry run changed nothing
    con.close()

    assert migrate.main(["--url", url, "--yes"]) == 0
    backups = list(tmp_path.glob("legacy.db.pre-migration-*.bak"))
    assert len(backups) == 1
    bak = sqlite3.connect(backups[0])
    assert {t: bak.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in migrations.BASELINE_TABLES} == counts
    assert "users" not in {r[0] for r in bak.execute("SELECT name FROM sqlite_master")}  # backup = pre-migration state
    bak.close()
    with pytest.raises(FileExistsError):
        migrate.backup_sqlite(path, backups[0])


def test_migrating_an_empty_database_is_refused(tmp_path):
    path = tmp_path / "empty.db"
    sqlite3.connect(path).close()
    with pytest.raises(SystemExit):
        migrate.run_migration(f"sqlite:///{path.as_posix()}")
