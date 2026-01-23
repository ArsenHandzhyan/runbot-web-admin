#!/usr/bin/env python3
"""
Production demo data creation script for Render.com
Adds sample submissions with files to the production database
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database.db import DatabaseManager
from src.models.models import (
    Participant, Challenge, Submission, Event,
    ChallengeType, DistanceType, EventType, EventStatus, SubmissionStatus
)
from datetime import datetime, timedelta

def create_production_demo_data():
    """Create demo data for production environment"""
    # Use production database (PostgreSQL on Render)
    db_manager = DatabaseManager()
    db = db_manager.get_session()

    try:
        print("🎯 Creating production demo data...")

        # Check if demo data already exists
        existing_submissions = db.query(Submission).count()
        if existing_submissions > 0:
            print(f"ℹ️  Demo data already exists ({existing_submissions} submissions). Skipping creation.")
            return True

        # Create demo participants
        participants_data = [
            {
                'telegram_id': '111111111',
                'full_name': 'Алексей Петров',
                'birth_date': datetime(1995, 3, 15).date(),
                'phone': '+7-999-111-11-11',
                'start_number': 'P001'
            },
            {
                'telegram_id': '222222222',
                'full_name': 'Мария Иванова',
                'birth_date': datetime(1992, 7, 22).date(),
                'phone': '+7-999-222-22-22',
                'start_number': 'P002'
            },
            {
                'telegram_id': '333333333',
                'full_name': 'Дмитрий Сидоров',
                'birth_date': datetime(1988, 12, 5).date(),
                'phone': '+7-999-333-33-33',
                'start_number': 'P003'
            }
        ]

        participants = []
        for p_data in participants_data:
            participant = Participant(**p_data)
            db.add(participant)
            participants.append(participant)

        db.commit()

        # Create demo challenges
        challenges_data = [
            {
                'name': 'Отжимания 50 раз',
                'description': 'Выполните 50 отжиманий за тренировку',
                'challenge_type': ChallengeType.PUSH_UPS,
                'start_date': datetime.now() - timedelta(days=5),
                'end_date': datetime.now() + timedelta(days=10),
                'is_active': True
            },
            {
                'name': 'Бег 10 км',
                'description': 'Пробегите 10 километров за неделю',
                'challenge_type': ChallengeType.RUNNING,
                'start_date': datetime.now() - timedelta(days=3),
                'end_date': datetime.now() + timedelta(days=12),
                'is_active': True
            },
            {
                'name': 'Планка 3 минуты',
                'description': 'Удерживайте планку 3 минуты',
                'challenge_type': ChallengeType.PLANK,
                'start_date': datetime.now() - timedelta(days=7),
                'end_date': datetime.now() + timedelta(days=8),
                'is_active': True
            }
        ]

        challenges = []
        for c_data in challenges_data:
            challenge = Challenge(**c_data)
            db.add(challenge)
            challenges.append(challenge)

        db.commit()

        # Demo files (these would normally be uploaded to Cloudflare R2)
        # For demo purposes, we'll use placeholder filenames that match the R2 naming pattern
        demo_files = [
            'demo-text-001.txt',
            'demo-excel-001.xlsx',
            'demo-video-001.mp4',
            'demo-image-001.jpg',
            'demo-document-001.pdf',
            'demo-video-002.mp4'
        ]

        # Create demo submissions with files
        submissions_data = [
            {
                'participant': participants[0],
                'challenge': challenges[0],
                'result_value': 50.0,
                'result_unit': 'отжиманий',
                'comment': 'Отлично выполнил! Прилагаю фото тренировки.',
                'media_path': demo_files[0],
                'status': SubmissionStatus.APPROVED
            },
            {
                'participant': participants[1],
                'challenge': challenges[1],
                'result_value': 10.5,
                'result_unit': 'км',
                'comment': 'Пробежал 10.5 км! GPS трек во вложении.',
                'media_path': demo_files[1],
                'status': SubmissionStatus.APPROVED
            },
            {
                'participant': participants[2],
                'challenge': challenges[2],
                'result_value': 3.2,
                'result_unit': 'минуты',
                'comment': 'Удержал планку 3 минуты 12 секунд! Видео прилагаю.',
                'media_path': demo_files[2],
                'status': SubmissionStatus.PENDING
            },
            {
                'participant': participants[0],
                'challenge': challenges[1],
                'result_value': 8.7,
                'result_unit': 'км',
                'comment': 'Сегодняшняя пробежка. Фото с маршрута.',
                'media_path': demo_files[3],
                'status': SubmissionStatus.PENDING
            },
            {
                'participant': participants[1],
                'challenge': challenges[0],
                'result_value': 45.0,
                'result_unit': 'отжиманий',
                'comment': '45 отжиманий! Результаты тренировки в PDF.',
                'media_path': demo_files[4],
                'status': SubmissionStatus.PENDING
            },
            {
                'participant': participants[2],
                'challenge': challenges[1],
                'result_value': 12.3,
                'result_unit': 'км',
                'comment': 'Длинная пробежка! Видео с маршрута.',
                'media_path': demo_files[5],
                'status': SubmissionStatus.APPROVED
            }
        ]

        submissions = []
        for s_data in submissions_data:
            submission = Submission(
                participant_id=s_data['participant'].id,
                challenge_id=s_data['challenge'].id,
                result_value=s_data['result_value'],
                result_unit=s_data['result_unit'],
                comment=s_data['comment'],
                media_path=s_data['media_path'],
                status=s_data['status']
            )
            db.add(submission)
            submissions.append(submission)

        db.commit()

        print("✅ Production demo data created!")
        print(f"   • Participants: {len(participants)}")
        print(f"   • Challenges: {len(challenges)}")
        print(f"   • Submissions: {len(submissions)}")

        # Show created submissions
        print("\n📋 Demo submissions created:")
        for i, sub in enumerate(submissions, 1):
            status_emoji = "✅" if sub.status.value == 'approved' else "⏳" if sub.status.value == 'pending' else "❌"
            print(f"   {i}. {sub.participant.full_name} - {sub.challenge.name}")
            print(f"      Result: {sub.result_value} {sub.result_unit}")
            print(f"      File: {sub.media_path}")
            print(f"      Status: {status_emoji}")
            print()

        return True

    except Exception as e:
        print(f"❌ Error creating production demo data: {e}")
        db.rollback()
        return False

    finally:
        db.close()

if __name__ == "__main__":
    success = create_production_demo_data()
    if success:
        print("\n🎉 Demo data ready! Visit the moderation page to see submissions with files.")
    else:
        print("\n❌ Failed to create demo data.")