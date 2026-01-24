#!/usr/bin/env python3
"""Script to reset challenges and events in production database for testing cascade deletes.

Deletes all challenges and events (cascade will delete related registrations).
Then adds test data: one challenge per type, one event, and one tournament.
"""

import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from src.models.models import (
    Base, Challenge, ChallengeType, Event, EventType, DistanceType
)

def main():
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set")
        sys.exit(1)

    engine = create_engine(db_url, future=True)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Delete all challenges and events (cascade deletes registrations)
    print("Deleting all challenges and events (cascade deletes registrations)...")
    with SessionLocal() as session:
        session.execute(text("DELETE FROM challenges"))
        session.execute(text("DELETE FROM events"))
        session.commit()

    print("Adding test data...")

    # Add one challenge per type
    challenge_types = [ChallengeType.PUSH_UPS, ChallengeType.SQUATS, ChallengeType.PLANK, ChallengeType.RUNNING, ChallengeType.STEPS]
    for ctype in challenge_types:
        challenge = Challenge(
            name=f"Test {ctype.value.replace('_', ' ').title()} Challenge",
            description=f"Test challenge for {ctype.value}",
            challenge_type=ctype,
            start_date=datetime.now(),
            end_date=datetime.now() + (datetime.now().replace(day=7) - datetime.now()),
            is_active=True,
            created_at=datetime.now()
        )
        with SessionLocal() as session:
            session.add(challenge)
            session.commit()

    # Add one event (run event)
    event1 = Event(
        name="Test Run Event",
        description="Test running event",
        event_type=EventType.RUN_EVENT,
        distance_type=DistanceType.ADULT_RUN,
        start_date=datetime.now(),
        end_date=datetime.now() + (datetime.now().replace(day=7) - datetime.now()),
        registration_deadline=datetime.now() + (datetime.now().replace(day=6) - datetime.now()),
        max_participants=100,
        is_active=True,
        status="upcoming",
        created_at=datetime.now()
    )
    with SessionLocal() as session:
        session.add(event1)
        session.commit()

    # Add one tournament
    event2 = Event(
        name="Test Tournament",
        description="Test tournament",
        event_type=EventType.TOURNAMENT,
        start_date=datetime.now(),
        end_date=datetime.now() + (datetime.now().replace(day=7) - datetime.now()),
        registration_deadline=datetime.now() + (datetime.now().replace(day=6) - datetime.now()),
        max_participants=50,
        is_active=True,
        status="upcoming",
        created_at=datetime.now()
    )
    with SessionLocal() as session:
        session.add(event2)
        session.commit()

    print("Test data added. Now test deletion in the web UI.")

if __name__ == "__main__":
    main()