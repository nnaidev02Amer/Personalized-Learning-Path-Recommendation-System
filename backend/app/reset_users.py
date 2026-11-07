"""Remove every login account (administrator, students, demo users) after taking a verified backup.

    python -m backend.app.reset_users            # dry run: shows what would be removed, changes nothing
    python -m backend.app.reset_users --apply    # backup, then remove

What is removed
    * all rows of ``users`` and ``auth_sessions`` (every login, including the administrator)
    * the learner profile of each removed student login that is NOT part of the generated sample data
      (``is_synthetic = 0``), together with its enrolments, requests, progress, quiz attempts, activity and
      recommendation history (database cascade)

What is kept
    * courses, lessons, quizzes and prerequisites
    * the generated sample learners (``is_synthetic = 1``) and all of their history - the ML models train on them
    * learner profiles that never had a login

Before anything is deleted the SQLite file is copied with SQLite's online backup API into
``<database folder>/backups/`` and the copy is verified (integrity check and identical row counts).
Afterwards ``PRAGMA integrity_check`` / ``foreign_key_check`` must pass, otherwise the change is rolled back.
Create the single administrator again with ``python -m backend.app.create_admin``.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import make_url

from backend.app.config import get_settings
from backend.app.database import make_engine

TABLES = ("users", "auth_sessions", "students", "courses", "enrollments", "enrollment_requests",
          "quiz_attempts", "activity_logs", "recommendation_history")


def _sqlite_path(url: str) -> Path:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        raise SystemExit("Only SQLite databases are supported by this tool.")
    return Path(parsed.database)


def counts(conn: sqlite3.Connection) -> dict[str, int]:
    existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return {t: conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in TABLES if t in existing}


def backup(path: Path) -> Path:
    target_dir = path.parent / "backups"
    target_dir.mkdir(exist_ok=True)
    target = target_dir / f"{path.stem}.before-user-reset-{datetime.now():%Y%m%d-%H%M%S}.bak"
    source = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        dest = sqlite3.connect(target)
        try:
            source.backup(dest)
            ok = dest.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            same = counts(source) == counts(dest)
        finally:
            dest.close()
    finally:
        source.close()
    if not (ok and same):
        target.unlink(missing_ok=True)
        raise SystemExit("The backup could not be verified; nothing was changed.")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="really remove the accounts (default: dry run)")
    args = parser.parse_args(argv)

    url = get_settings().database_url
    path = _sqlite_path(url)
    if not path.exists():
        print(f"No database at {path}.", file=sys.stderr)
        return 1

    engine = make_engine(url)
    try:
        with engine.connect() as conn:
            if "users" not in {r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))}:
                print("This database has no users table (not migrated yet): nothing to remove.")
                return 0
            users = conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
            doomed = conn.execute(text(
                "SELECT s.id FROM students s JOIN users u ON u.student_id = s.id WHERE s.is_synthetic = 0")).scalars().all()
            sample_logins = conn.execute(text(
                "SELECT COUNT(*) FROM users u JOIN students s ON s.id = u.student_id WHERE s.is_synthetic = 1")).scalar()
        print(f"Database: {path}")
        print(f"Login accounts to remove: {users} ({sample_logins} of them attached to sample learners, "
              f"whose profiles are kept)")
        print(f"Learner profiles to remove with their login: {len(doomed)}")
        if not args.apply:
            print("Dry run only. Re-run with --apply to back up and remove.")
            return 0

        saved = backup(path)
        print(f"Backup written and verified: {saved}")

        with engine.begin() as conn:
            before = {t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar() for t in ("courses", "students")}
            conn.execute(text("DELETE FROM auth_sessions"))
            if doomed:
                conn.execute(text("DELETE FROM students WHERE id IN (SELECT student_id FROM users) AND is_synthetic = 0"))
            conn.execute(text("DELETE FROM users"))
            problems = conn.execute(text("PRAGMA foreign_key_check")).all()
            integrity = conn.execute(text("PRAGMA integrity_check")).scalar()
            courses = conn.execute(text("SELECT COUNT(*) FROM courses")).scalar()
            if problems or integrity != "ok" or courses != before["courses"]:
                raise RuntimeError(f"Verification failed ({integrity}, {len(problems)} FK problems); rolled back")
        with sqlite3.connect(path) as raw:
            after = counts(raw)
        print("Done. Row counts now:", ", ".join(f"{k}={v}" for k, v in after.items()))
        print("Next: python -m backend.app.create_admin --email <you> --generate-password")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
