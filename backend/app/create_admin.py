"""Create the first administrator (or reset an administrator's password).

    python -m backend.app.create_admin --email you@example.com
    python -m backend.app.create_admin --email you@example.com --generate-password
    python -m backend.app.create_admin --email you@example.com --reset-password

There is exactly ONE administrator: creating a second one is refused here and by a database constraint.

The password is read from a hidden prompt (or from standard input with ``--password-stdin`` for
scripted setups). There is no default administrator and no password is ever read from the environment
or written to a file. The database is created if it does not exist yet; an existing pre-authentication
database must be migrated first (``python -m backend.app.migrate``).
"""

from __future__ import annotations

import argparse
import getpass
import re
import secrets
import sys

from sqlalchemy import select

from backend.app.config import get_settings
from backend.app.database import Database
from backend.app.models import User
from backend.app.security import hash_password, password_problems

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--email", required=True)
    parser.add_argument("--reset-password", action="store_true", help="change the password of an existing admin")
    parser.add_argument("--generate-password", action="store_true",
                        help="generate a strong random password and print it once")
    parser.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    args = parser.parse_args(argv)

    email = args.email.strip().lower()
    if not EMAIL.match(email):
        print("That does not look like an e-mail address.", file=sys.stderr)
        return 2

    generated = args.generate_password
    if generated:
        password = secrets.token_urlsafe(18)
    elif args.password_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
    else:
        password = getpass.getpass("New admin password: ")
        if password != getpass.getpass("Repeat password: "):
            print("The passwords do not match.", file=sys.stderr)
            return 2
    problems = password_problems(password, email=email)
    if problems:
        print("Password rejected: it " + "; it ".join(problems) + ".", file=sys.stderr)
        return 2

    database = Database(get_settings().database_url)
    try:
        database.create_all()                       # creates a brand-new DB; refuses an un-migrated one
        with database.SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            existing_admin = db.scalar(select(User).where(User.role == "admin"))
            if user is None:
                if args.reset_password:
                    print("No such account.", file=sys.stderr)
                    return 1
                if existing_admin is not None:
                    print(f"An administrator already exists ({existing_admin.email}). Only one is allowed; "
                          "use --reset-password with that e-mail to change its password.", file=sys.stderr)
                    return 1
                db.add(User(email=email, password_hash=hash_password(password), role="admin"))
                print(f"Administrator {email} created.")
            else:
                if not args.reset_password:
                    print("An account with that e-mail already exists (use --reset-password).", file=sys.stderr)
                    return 1
                if user.role != "admin":
                    print("That account is not an administrator.", file=sys.stderr)
                    return 1
                user.password_hash, user.failed_logins, user.locked_until, user.is_active = \
                    hash_password(password), 0, None, True
                print(f"Password for {email} reset.")
            db.commit()
        if generated:
            print(f"Password (shown once, store it safely): {password}")
    finally:
        database.engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
