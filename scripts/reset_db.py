#!/usr/bin/env python3
"""Reset the database to a clean state based on current ORM models.

This will drop all tables and recreate them from the SQLAlchemy models.
Use only in test/staging environments or when you explicitly want to
start from a clean database in production (data will be lost).
"""

import os
from sqlalchemy import create_engine
from src.models.models import Base


def main():
    db_url = os.getenv("DATABASE_URL", None)
    if not db_url:
        raise SystemExit("DATABASE_URL environment variable is not set")

    engine = create_engine(db_url, future=True)

    print(f"Resetting database: {db_url}")
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Recreating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Database reset complete.")


if __name__ == "__main__":
    main()
