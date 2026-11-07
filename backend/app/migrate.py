"""Upgrade an existing database to the latest schema, safely.

    python -m backend.app.migrate --dry-run     # rehearse on a temporary COPY; changes nothing
    python -m backend.app.migrate               # back up, then migrate (asks for confirmation)
    python -m backend.app.migrate --yes         # same, without the prompt
    python -m backend.app.migrate --url sqlite:///path/to/other.db

What it does for a database created before authentication existed ("legacy"):

1. copies the SQLite file to ``<name>.pre-migration-<UTC timestamp>.bak`` (never overwrites a file);
2. records every table's row count and runs ``PRAGMA integrity_check``;
3. stamps the baseline revision (no DDL: the pre-authentication tables already exist);
4. applies the additive revision(s): new tables + ``courses.is_active`` (default: active);
5. verifies that every pre-existing table kept exactly the same number of rows and that
   ``PRAGMA integrity_check`` / ``foreign_key_check`` still pass.

It never deletes data, never re-creates a table that holds data, and never touches a database it was
not pointed at.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from backend.app import migrations
from backend.app.config import get_settings


def sqlite_path(url: str) -> Path:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        raise SystemExit("backup-aware migration is implemented for file-based SQLite databases only")
    return Path(parsed.database)


def backup_sqlite(src: Path, dest: Path) -> None:
    """Consistent copy using SQLite's online backup API (safe even while the DB is in use)."""
    if dest.exists():
        raise FileExistsError(f"refusing to overwrite {dest}")
    source = sqlite3.connect(f"file:{src.as_posix()}?mode=ro", uri=True)
    target = sqlite3.connect(dest)
    with target:
        source.backup(target)
    source.close()
    target.close()


def table_counts(engine) -> dict[str, int]:
    names = [t for t in inspect(engine).get_table_names() if t not in ("sqlite_sequence", "alembic_version")]
    with engine.connect() as conn:
        return {t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in sorted(names)}


def health(engine) -> dict:
    with engine.connect() as conn:
        return {"integrity_check": conn.execute(text("PRAGMA integrity_check")).scalar(),
                "foreign_key_violations": len(conn.execute(text("PRAGMA foreign_key_check")).fetchall())}


def run_migration(url: str) -> dict:
    """Migrate ``url`` in place (the caller makes the backup). Returns a verification report."""
    engine = create_engine(url)
    try:
        state = migrations.schema_state(engine)
        report = {"state_before": state, "revision_before": migrations.current_revision(engine)}
        if state == "empty":
            raise SystemExit("The database is empty: start the application (or `python -m backend.app.seed`) "
                             "to create it. Nothing to migrate.")
        if state == "current":
            report.update(state_after="current", changed=False)
            return report
        before_counts, before_health = table_counts(engine), health(engine)
        if state == "legacy":
            missing = set(migrations.BASELINE_TABLES) - set(before_counts)
            if missing:
                raise SystemExit(f"Not a recognised pre-authentication database (missing tables: {sorted(missing)}).")
            migrations.stamp(engine, migrations.BASELINE)
        migrations.upgrade(engine)
        after_counts, after_health = table_counts(engine), health(engine)
        changed_rows = {t: (n, after_counts.get(t)) for t, n in before_counts.items() if after_counts.get(t) != n}
        report.update(
            state_after=migrations.schema_state(engine), revision_after=migrations.current_revision(engine),
            changed=True, rows_before=before_counts, rows_after=after_counts, rows_changed=changed_rows,
            health_before=before_health, health_after=after_health,
            ok=(not changed_rows and after_health["integrity_check"] == "ok"
                and after_health["foreign_key_violations"] == before_health["foreign_key_violations"]))
        return report
    finally:
        engine.dispose()


def _print(report: dict) -> None:
    print(f"  schema before : {report['state_before']} (revision {report['revision_before']})")
    if not report.get("changed"):
        print("  nothing to do: the database is already at the latest revision")
        return
    print(f"  schema after  : {report['state_after']} (revision {report['revision_after']})")
    for table, n in report["rows_before"].items():
        print(f"    {table:<22} {n:>7} rows -> {report['rows_after'][table]:>7}")
    new = sorted(set(report["rows_after"]) - set(report["rows_before"]))
    print(f"  new tables    : {', '.join(new) or '-'}")
    print(f"  integrity     : {report['health_after']}")
    print("  RESULT        :", "OK - all existing rows preserved" if report["ok"] else "VERIFICATION FAILED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely migrate the application database.")
    parser.add_argument("--url", help="database URL (default: DATABASE_URL / data/app.db)")
    parser.add_argument("--dry-run", action="store_true", help="rehearse on a temporary copy; change nothing")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)

    url = args.url or get_settings().database_url
    path = sqlite_path(url)
    if not path.exists():
        raise SystemExit(f"Database file not found: {path}")
    print(f"Database: {path}")

    if args.dry_run:
        with tempfile.TemporaryDirectory(prefix="plrs-migrate-") as tmp:
            copy = Path(tmp) / "rehearsal.db"
            backup_sqlite(path, copy)
            print("DRY RUN on a temporary copy (the real database is not touched):")
            report = run_migration(f"sqlite:///{copy.as_posix()}")
            _print(report)
            return 0 if report.get("ok", True) else 1

    engine = create_engine(url)
    state = migrations.schema_state(engine)
    engine.dispose()
    if state == "current":
        print("Already at the latest revision. Nothing to do.")
        return 0
    if not args.yes and input(f"Migrate this database ({state})? A backup is made first. [y/N] ").strip().lower() != "y":
        print("Cancelled. Nothing was changed.")
        return 1
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.name}.pre-migration-{stamp}.bak")
    backup_sqlite(path, backup)
    print(f"Backup written: {backup}")
    try:
        report = run_migration(url)
    except BaseException:
        print(f"Migration failed. Your original data is in the backup: {backup}", file=sys.stderr)
        raise
    _print(report)
    if not report.get("ok", True):
        print(f"Verification failed - restore from {backup}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
