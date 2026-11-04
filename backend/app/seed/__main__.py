"""Create / reset the database and load the sample data.

    python -m backend.app.seed            # seed only if the database is empty
    python -m backend.app.seed --reset    # drop all tables, recreate and reseed
"""

import argparse

from backend.app.config import get_settings
from backend.app.database import Database
from backend.app.seed.generator import database_counts, seed_database


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    args = parser.parse_args()

    settings = get_settings()
    database = Database(settings.database_url)
    if args.reset:
        database.drop_all()
    database.create_all()
    with database.SessionLocal() as db:
        if database_counts(db)["courses"] and not args.reset:
            print("Database already seeded:", database_counts(db))
            return
        print("Seeded:", seed_database(db, random_state=settings.seed_random_state))
    print("Database:", settings.database_url)


if __name__ == "__main__":
    main()
