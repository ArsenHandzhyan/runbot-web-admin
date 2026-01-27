"""
Statistics Engine
Automatically calculates and updates participant statistics
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from collections import defaultdict
from sqlalchemy import func

from src.models.models import (
    Participant, Challenge, Submission, ParticipantStats, 
    SubmissionStatus, ChallengeType, DistanceType
)
from src.database.db import DatabaseManager

logger = logging.getLogger(__name__)

class StatisticsEngine:
    """Engine for calculating and managing statistics"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
    
    def update_all_statistics(self):
        """Update statistics for all participants"""
        logger.info("Starting statistics update...")
        
        db = self.db_manager.get_session()
        try:
            # Get all participants
            participants = db.query(Participant).filter(Participant.is_active == True).all()
            
            updated_count = 0
            for participant in participants:
                if self._update_participant_statistics(db, participant.id):
                    updated_count += 1
            
            db.commit()
            logger.info(f"Statistics updated for {updated_count} participants")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating statistics: {e}")
        finally:
            db.close()
    
    def _update_participant_statistics(self, db, participant_id: int) -> bool:
        """Update statistics for a specific participant"""
        try:
            # Get participant submissions
            submissions = db.query(Submission).filter(
                Submission.participant_id == participant_id,
                Submission.status == SubmissionStatus.APPROVED
            ).all()
            
            if not submissions:
                return False
            
            # Calculate basic statistics
            total_submissions = len(submissions)
            approved_submissions = len([s for s in submissions if s.status == SubmissionStatus.APPROVED])
            
            # Calculate total score (sum of all results)
            total_score = sum(s.result_value or 0 for s in submissions)
            average_score = total_score / approved_submissions if approved_submissions > 0 else 0
            
            # Calculate streak (consecutive days)
            streak_days = self._calculate_streak(submissions)
            
            # Get last submission date
            last_submission = max(submissions, key=lambda x: x.submission_date) if submissions else None
            last_submission_date = last_submission.submission_date if last_submission else None
            
            # Update or create stats record
            stats = db.query(ParticipantStats).filter(
                ParticipantStats.participant_id == participant_id
            ).first()
            
            if not stats:
                stats = ParticipantStats(participant_id=participant_id)
                db.add(stats)
            
            stats.total_submissions = total_submissions
            stats.approved_submissions = approved_submissions
            stats.total_score = total_score
            stats.average_score = average_score
            stats.streak_days = streak_days
            stats.last_submission_date = last_submission_date
            stats.updated_at = datetime.now()
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating participant {participant_id} statistics: {e}")
            return False
    
    def _calculate_participant_streak(self, db, participant_id: int) -> int:
        """Calculate consecutive days streak for a participant"""
        try:
            # Get approved submissions ordered by date
            submissions = db.query(Submission).filter(
                Submission.participant_id == participant_id,
                Submission.status == SubmissionStatus.APPROVED
            ).order_by(Submission.submission_date).all()
            
            if not submissions:
                return 0
            
            # Get unique dates
            dates_with_activity = set()
            for sub in submissions:
                dates_with_activity.add(sub.submission_date.date())
            
            activity_dates = sorted(list(dates_with_activity))
            
            if not activity_dates:
                return 0
            
            # Calculate streak
            current_streak = 1
            max_streak = 1
            
            for i in range(1, len(activity_dates)):
                if (activity_dates[i] - activity_dates[i-1]).days == 1:
                    current_streak += 1
                    max_streak = max(max_streak, current_streak)
                else:
                    current_streak = 1
            
            return max_streak
            
        except Exception as e:
            logger.error(f"Error calculating streak for participant {participant_id}: {e}")
            return 0
    
    def _calculate_streak(self, submissions: List[Submission]) -> int:
        """Calculate consecutive days streak"""
        if not submissions:
            return 0
        
        # Sort submissions by date
        sorted_subs = sorted(submissions, key=lambda x: x.submission_date.date())
        
        # Group by date
        dates_with_activity = set()
        for sub in sorted_subs:
            dates_with_activity.add(sub.submission_date.date())
        
        # Convert to sorted list
        activity_dates = sorted(list(dates_with_activity))
        
        # Calculate streak
        if not activity_dates:
            return 0
        
        current_streak = 1
        max_streak = 1
        
        for i in range(1, len(activity_dates)):
            if (activity_dates[i] - activity_dates[i-1]).days == 1:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 1
        
        return max_streak
    
    def get_leaderboard(self, challenge_type: Optional[ChallengeType] = None, 
                       limit: int = 10) -> List[Dict]:
        """Get leaderboard for participants"""
        db = self.db_manager.get_session()
        try:
            # First, let's calculate leaderboard based on approved submissions
            # since ParticipantStats might not be populated
            
            # Get all approved submissions with participant info
            query = db.query(
                Participant.id,
                Participant.full_name,
                Participant.start_number,
                Participant.distance_type,
                func.sum(Submission.result_value).label('total_score'),
                func.count(Submission.id).label('submission_count'),
                func.avg(Submission.result_value).label('average_score')
            ).join(Submission).filter(
                Participant.is_active == True,
                Submission.status == SubmissionStatus.APPROVED
            ).group_by(
                Participant.id,
                Participant.full_name,
                Participant.start_number,
                Participant.distance_type
            ).order_by(func.sum(Submission.result_value).desc())
            
            if challenge_type:
                # Filter by specific challenge type
                query = query.join(Challenge).filter(
                    Challenge.challenge_type == challenge_type
                )
            
            results = query.limit(limit).all()
            
            leaderboard = []
            for i, (participant_id, name, number, distance_type, total_score, submission_count, avg_score) in enumerate(results, 1):
                # Calculate streak for this participant
                streak = self._calculate_participant_streak(db, participant_id)
                
                leaderboard.append({
                    'position': i,
                    'name': name,
                    'start_number': number,
                    'distance': 'Взрослая' if distance_type == DistanceType.ADULT_RUN else 'Детская',
                    'total_score': round(float(total_score or 0), 2),
                    'submissions': submission_count,
                    'average_score': round(float(avg_score or 0), 2),
                    'streak': streak
                })
            
            return leaderboard
            
        except Exception as e:
            logger.error(f"Error getting leaderboard: {e}")
            return []
        finally:
            db.close()
    
    def get_period_statistics(self, start_date: datetime, end_date: datetime) -> Dict:
        """Get statistics for a specific period"""
        db = self.db_manager.get_session()
        try:
            # Get submissions in period
            submissions = db.query(Submission).filter(
                Submission.submission_date >= start_date,
                Submission.submission_date <= end_date,
                Submission.status == SubmissionStatus.APPROVED
            ).all()
            
            # Get unique participants
            participant_ids = set(s.participant_id for s in submissions)
            
            # Calculate statistics
            total_submissions = len(submissions)
            unique_participants = len(participant_ids)
            
            # Group by challenge type
            challenge_stats = defaultdict(lambda: {'count': 0, 'total_score': 0})
            challenge_ids = {s.challenge_id for s in submissions}
            challenges = {}
            if challenge_ids:
                rows = db.query(Challenge).filter(Challenge.id.in_(challenge_ids)).all()
                challenges = {c.id: c for c in rows}
            for sub in submissions:
                challenge = challenges.get(sub.challenge_id)
                if challenge:
                    challenge_stats[challenge.challenge_type.value]['count'] += 1
                    challenge_stats[challenge.challenge_type.value]['total_score'] += sub.result_value or 0
            
            # Average submissions per participant
            avg_submissions_per_participant = total_submissions / unique_participants if unique_participants > 0 else 0
            
            return {
                'period': {
                    'start': start_date.strftime('%d.%m.%Y'),
                    'end': end_date.strftime('%d.%m.%Y')
                },
                'total_submissions': total_submissions,
                'unique_participants': unique_participants,
                'avg_submissions_per_participant': round(avg_submissions_per_participant, 2),
                'challenge_distribution': dict(challenge_stats)
            }
            
        except Exception as e:
            logger.error(f"Error getting period statistics: {e}")
            return {}
        finally:
            db.close()
    
    def get_participant_detailed_stats(self, participant_id: int) -> Dict:
        """Get detailed statistics for a specific participant"""
        db = self.db_manager.get_session()
        try:
            participant = db.query(Participant).get(participant_id)
            if not participant:
                return {}
            
            # Get all submissions
            submissions = db.query(Submission).filter(
                Submission.participant_id == participant_id
            ).all()
            
            # Group by challenge type
            challenge_stats = defaultdict(list)
            challenge_ids = {s.challenge_id for s in submissions}
            challenges = {}
            if challenge_ids:
                rows = db.query(Challenge).filter(Challenge.id.in_(challenge_ids)).all()
                challenges = {c.id: c for c in rows}
            for sub in submissions:
                challenge = challenges.get(sub.challenge_id)
                if challenge:
                    challenge_stats[challenge.challenge_type.value].append({
                        'date': sub.submission_date.strftime('%d.%m.%Y'),
                        'result': sub.result_value,
                        'unit': sub.result_unit,
                        'status': sub.status.value
                    })
            
            # Calculate trends
            weekly_progress = self._calculate_weekly_progress(submissions)
            
            return {
                'participant_info': {
                    'name': participant.full_name,
                    'start_number': participant.start_number,
                    'distance_type': participant.distance_type.value
                },
                'overall_stats': {
                    'total_submissions': len(submissions),
                    'approved_submissions': len([s for s in submissions if s.status == SubmissionStatus.APPROVED]),
                    'pending_submissions': len([s for s in submissions if s.status == SubmissionStatus.PENDING]),
                    'rejected_submissions': len([s for s in submissions if s.status == SubmissionStatus.REJECTED])
                },
                'challenge_breakdown': dict(challenge_stats),
                'weekly_progress': weekly_progress
            }
            
        except Exception as e:
            logger.error(f"Error getting participant detailed stats: {e}")
            return {}
        finally:
            db.close()
    
    def _calculate_weekly_progress(self, submissions: List[Submission]) -> List[Dict]:
        """Calculate weekly progress based on submissions"""
        if not submissions:
            return []
        
        # Sort by date
        sorted_subs = sorted(submissions, key=lambda x: x.submission_date)
        
        # Group by week
        weekly_data = defaultdict(list)
        for sub in sorted_subs:
            week_start = sub.submission_date - timedelta(days=sub.submission_date.weekday())
            week_key = week_start.strftime('%Y-%W')
            weekly_data[week_key].append(sub.result_value or 0)
        
        # Calculate averages
        progress = []
        for week_key, values in sorted(weekly_data.items()):
            year, week_num = week_key.split('-')
            progress.append({
                'week': f"Неделя {week_num}, {year}",
                'submissions_count': len(values),
                'average_result': round(sum(values) / len(values), 2) if values else 0,
                'total_result': round(sum(values), 2)
            })
        
        return progress
    
    def schedule_regular_updates(self):
        """Schedule regular statistics updates"""
        import schedule
        import time
        
        # Schedule daily update at 1 AM
        schedule.every().day.at("01:00").do(self.update_all_statistics)
        
        # Schedule weekly update on Sundays at 2 AM
        schedule.every().sunday.at("02:00").do(self.update_all_statistics)
        
        logger.info("Statistics update scheduler started")
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute