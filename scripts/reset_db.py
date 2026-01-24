#!/usr/bin/env python3
"""Reset the database to a clean state based on current ORM models.

This will drop all tables and recreate them from the SQLAlchemy models.
Use only in test/staging environments or when you explicitly want to
start from a clean database in production (data will be lost).
"""

import os
import sys
import subprocess
from datetime import datetime
from sqlalchemy import create_engine
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from src.models.models import Base


def main():
    db_url = os.getenv("DATABASE_URL", None)
    if not db_url:
        raise SystemExit("DATABASE_URL environment variable is not set")

    engine = create_engine(db_url, future=True)

    # Create a backup before destructive reset (best effort, in production this is critical)
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_file = f"backup_{date_str}.sql.gz"
    try:
        print(f"Creating backup: {backup_file}")
        # pg_dump accepts a connection URL as the database argument
        subprocess.run(f"pg_dump '{db_url}' | gzip > '{backup_file}'", shell=True, check=True)
        print("Backup created successfully.")
    except Exception as e:
        print(f"Warning: could not create backup: {e}")

    print(f"Resetting database: {db_url}")
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Database reset complete.")


if __name__ == "__main__":
    main()
