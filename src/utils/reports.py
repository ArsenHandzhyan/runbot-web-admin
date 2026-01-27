"""
Reports and Analytics Module
Generates detailed reports and exports data to Excel format
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from io import BytesIO
from sqlalchemy import func

from src.models.models import (
    Participant, Challenge, Submission, ParticipantStats,
    SubmissionStatus, ChallengeType, DistanceType
)
from src.database.db import DatabaseManager
from src.utils.statistics import StatisticsEngine

logger = logging.getLogger(__name__)

class ReportGenerator:
    """Generates various reports and analytics"""
    
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager
        self.stats_engine = StatisticsEngine(db_manager)
    
    def generate_participants_report(self) -> BytesIO:
        """Generate full participants report in Excel format"""
        logger.info("Generating participants report...")
        
        db = self.db_manager.get_session()
        try:
            # Get all participants with their stats
            participants_data = db.query(
                Participant.id,
                Participant.full_name,
                Participant.birth_date,
                Participant.phone,
                Participant.distance_type,
                Participant.start_number,
                Participant.registration_date,
                Participant.is_active,
                ParticipantStats.total_submissions,
                ParticipantStats.approved_submissions,
                ParticipantStats.total_score,
                ParticipantStats.average_score,
                ParticipantStats.streak_days,
                ParticipantStats.last_submission_date
            ).outerjoin(ParticipantStats).all()
            
            # Convert to DataFrame
            df = pd.DataFrame(participants_data, columns=[
                'ID', 'ФИО', 'Дата рождения', 'Телефон', 'Дистанция',
                'Стартовый номер', 'Дата регистрации', 'Активен',
                'Всего отчетов', 'Одобренных отчетов', 'Общий балл',
                'Средний балл', 'Серия дней', 'Последняя активность'
            ])
            
            # Process data
            df['Дистанция'] = df['Дистанция'].map({
                'adult_run': 'Взрослая',
                'children_run': 'Детская'
            })
            
            df['Активен'] = df['Активен'].map({True: 'Да', False: 'Нет'})
            df['Дата рождения'] = pd.to_datetime(df['Дата рождения']).dt.strftime('%d.%m.%Y')
            df['Дата регистрации'] = pd.to_datetime(df['Дата регистрации']).dt.strftime('%d.%m.%Y')
            
            # Fill NaN values
            df = df.fillna({
                'Всего отчетов': 0,
                'Одобренных отчетов': 0,
                'Общий балл': 0,
                'Средний балл': 0,
                'Серия дней': 0,
                'Последняя активность': 'Нет данных'
            })
            
            # Create Excel file in memory
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Main sheet
                df.to_excel(writer, sheet_name='Участники', index=False)
                
                # Summary sheet
                summary_data = {
                    'Показатель': [
                        'Всего участников',
                        'Активных участников',
                        'Участников взрослой дистанции',
                        'Участников детской дистанции',
                        'Среднее количество отчетов',
                        'Средний балл',
                        'Максимальная серия дней'
                    ],
                    'Значение': [
                        len(df),
                        len(df[df['Активен'] == 'Да']),
                        len(df[df['Дистанция'] == 'Взрослая']),
                        len(df[df['Дистанция'] == 'Детская']),
                        round(df['Всего отчетов'].mean(), 2),
                        round(df['Общий балл'].mean(), 2),
                        df['Серия дней'].max()
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Сводка', index=False)
            
            output.seek(0)
            logger.info("Participants report generated successfully")
            return output
            
        except Exception as e:
            logger.error(f"Error generating participants report: {e}")
            raise
        finally:
            db.close()
    
    def generate_submissions_report(self, start_date: Optional[datetime] = None,
                                  end_date: Optional[datetime] = None) -> BytesIO:
        """Generate submissions report with filtering by date"""
        logger.info("Generating submissions report...")
        
        db = self.db_manager.get_session()
        try:
            # Build query with date filtering
            query = db.query(
                Submission.id,
                Participant.full_name,
                Participant.start_number,
                Participant.distance_type,
                Challenge.name.label('challenge_name'),
                Challenge.challenge_type,
                Submission.result_value,
                Submission.result_unit,
                Submission.comment,
                Submission.status,
                Submission.submission_date
            ).join(Participant).join(Challenge)
            
            if start_date:
                query = query.filter(Submission.submission_date >= start_date)
            if end_date:
                query = query.filter(Submission.submission_date <= end_date)
            
            submissions_data = query.order_by(Submission.submission_date.desc()).all()
            
            # Convert to DataFrame
            df = pd.DataFrame(submissions_data, columns=[
                'ID', 'Участник', 'Стартовый номер', 'Дистанция', 'Челлендж',
                'Тип челленджа', 'Результат', 'Единица', 'Комментарий', 'Статус', 'Дата'
            ])
            
            # Process data
            df['Дистанция'] = df['Дистанция'].map({
                'adult_run': 'Взрослая',
                'children_run': 'Детская'
            })
            
            df['Тип челленджа'] = df['Тип челленджа'].map({
                'push_ups': 'Отжимания',
                'squats': 'Приседания',
                'plank': 'Планка',
                'running': 'Бег',
                'steps': 'Шаги'
            })
            
            df['Статус'] = df['Статус'].map({
                'pending': 'На проверке',
                'approved': 'Одобрено',
                'rejected': 'Отклонено'
            })
            
            df['Дата'] = pd.to_datetime(df['Дата']).dt.strftime('%d.%m.%Y %H:%M')
            
            # Create Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Отчеты', index=False)
                
                # Add summary statistics
                status_counts = df['Статус'].value_counts()
                challenge_counts = df['Тип челленджа'].value_counts()
                
                summary_stats = pd.DataFrame({
                    'Категория': ['Всего отчетов'] + list(status_counts.index) + [''] +
                               ['Распределение по типам'] + list(challenge_counts.index),
                    'Количество': [len(df)] + list(status_counts.values) + [''] +
                                [''] + list(challenge_counts.values)
                })
                
                summary_stats.to_excel(writer, sheet_name='Статистика', index=False)
            
            output.seek(0)
            logger.info("Submissions report generated successfully")
            return output
            
        except Exception as e:
            logger.error(f"Error generating submissions report: {e}")
            raise
        finally:
            db.close()
    
    def generate_leaderboard_report(self, challenge_type: Optional[ChallengeType] = None,
                                  limit: int = 50) -> BytesIO:
        """Generate leaderboard report"""
        logger.info("Generating leaderboard report...")
        
        try:
            # Get leaderboard data
            leaderboard = self.stats_engine.get_leaderboard(challenge_type, limit)
            
            if not leaderboard:
                # Return empty report
                output = BytesIO()
                df = pd.DataFrame(columns=['Позиция', 'Имя', 'Стартовый номер', 'Дистанция', 
                                         'Общий балл', 'Отчетов', 'Средний балл', 'Серия'])
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, sheet_name='Рейтинг', index=False)
                output.seek(0)
                return output
            
            # Convert to DataFrame
            df = pd.DataFrame(leaderboard)
            
            # Reorder and rename columns
            df = df[['position', 'name', 'start_number', 'distance', 'total_score', 
                    'submissions', 'average_score', 'streak']]
            df.columns = ['Позиция', 'Имя', 'Стартовый номер', 'Дистанция', 
                         'Общий балл', 'Отчетов', 'Средний балл', 'Серия']
            
            # Create Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Рейтинг', index=False)
                
                # Add summary
                summary_data = {
                    'Показатель': ['Всего в рейтинге', 'Средний балл', 'Максимальный балл', 
                                 'Средняя серия', 'Максимальная серия'],
                    'Значение': [
                        len(df),
                        round(df['Общий балл'].mean(), 2),
                        df['Общий балл'].max(),
                        round(df['Серия'].mean(), 1),
                        df['Серия'].max()
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Сводка', index=False)
            
            output.seek(0)
            logger.info("Leaderboard report generated successfully")
            return output
            
        except Exception as e:
            logger.error(f"Error generating leaderboard report: {e}")
            raise
    
    def generate_activity_report(self, days: int = 30) -> BytesIO:
        """Generate activity report for the last N days"""
        logger.info(f"Generating activity report for last {days} days...")
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        db = self.db_manager.get_session()
        try:
            # Get daily activity data
            daily_stats = []

            rows = db.query(
                func.date(Submission.submission_date).label('day'),
                func.count(Submission.id),
                func.count(func.distinct(Submission.participant_id))
            ).filter(
                Submission.submission_date >= start_date,
                Submission.submission_date < end_date,
                Submission.status == SubmissionStatus.APPROVED
            ).group_by(func.date(Submission.submission_date)).all()

            stats_by_day = {row.day: {'submissions': row[1], 'participants': row[2]} for row in rows}

            for i in range(days):
                day = (start_date + timedelta(days=i)).date()
                stats = stats_by_day.get(day, {'submissions': 0, 'participants': 0})
                daily_stats.append({
                    'date': day.strftime('%d.%m.%Y'),
                    'submissions': stats['submissions'],
                    'participants': stats['participants']
                })
            
            # Convert to DataFrame
            df = pd.DataFrame(daily_stats)
            
            # Create Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, sheet_name='Активность по дням', index=False)
                
                # Add charts data preparation
                chart_data = df.copy()
                chart_data['Дата'] = pd.to_datetime(chart_data['date'], format='%d.%m.%Y')
                chart_data = chart_data.sort_values('Дата')
                
                # Weekly aggregation
                chart_data['Неделя'] = chart_data['Дата'].dt.isocalendar().week
                chart_data['Год'] = chart_data['Дата'].dt.year
                weekly_stats = chart_data.groupby(['Год', 'Неделя']).agg({
                    'submissions': 'sum',
                    'participants': 'mean'
                }).reset_index()
                
                weekly_stats.to_excel(writer, sheet_name='По неделям', index=False)
            
            output.seek(0)
            logger.info("Activity report generated successfully")
            return output
            
        except Exception as e:
            logger.error(f"Error generating activity report: {e}")
            raise
        finally:
            db.close()
    
    def generate_challenge_performance_report(self) -> BytesIO:
        """Generate detailed challenge performance report"""
        logger.info("Generating challenge performance report...")
        
        db = self.db_manager.get_session()
        try:
            # Get all challenges with their performance metrics
            challenges_data = []
            
            challenges = db.query(Challenge).all()

            # Prefetch approved submissions for all challenges
            challenge_ids = [c.id for c in challenges]
            submissions = []
            if challenge_ids:
                submissions = db.query(Submission).filter(
                    Submission.challenge_id.in_(challenge_ids),
                    Submission.status == SubmissionStatus.APPROVED
                ).all()

            submissions_by_challenge = {}
            for s in submissions:
                submissions_by_challenge.setdefault(s.challenge_id, []).append(s)

            for challenge in challenges:
                challenge_submissions = submissions_by_challenge.get(challenge.id, [])

                if challenge_submissions:
                    total_results = [s.result_value for s in challenge_submissions if s.result_value]
                    avg_result = sum(total_results) / len(total_results) if total_results else 0
                    max_result = max(total_results) if total_results else 0

                    challenges_data.append({
                        'Название': challenge.name,
                        'Тип': self._translate_challenge_type(challenge.challenge_type),
                        'Активен': 'Да' if challenge.is_active else 'Нет',
                        'Отчетов': len(challenge_submissions),
                        'Средний результат': round(avg_result, 2),
                        'Максимальный результат': max_result,
                        'Единица измерения': challenge_submissions[0].result_unit if challenge_submissions else ''
                    })
            
            # Convert to DataFrame
            df = pd.DataFrame(challenges_data)
            
            # Create Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                if not df.empty:
                    df.to_excel(writer, sheet_name='Производительность', index=False)
                    
                    # Add summary by challenge type
                    type_summary = df.groupby('Тип').agg({
                        'Отчетов': 'sum',
                        'Средний результат': 'mean'
                    }).round(2)
                    
                    type_summary.to_excel(writer, sheet_name='По типам')
                else:
                    # Empty report
                    empty_df = pd.DataFrame(columns=['Название', 'Тип', 'Активен', 'Отчетов', 
                                                   'Средний результат', 'Максимальный результат', 'Единица измерения'])
                    empty_df.to_excel(writer, sheet_name='Производительность', index=False)
            
            output.seek(0)
            logger.info("Challenge performance report generated successfully")
            return output
            
        except Exception as e:
            logger.error(f"Error generating challenge performance report: {e}")
            raise
        finally:
            db.close()
    
    def _translate_challenge_type(self, challenge_type: ChallengeType) -> str:
        """Translate challenge type to Russian"""
        translations = {
            ChallengeType.PUSH_UPS: 'Отжимания',
            ChallengeType.SQUATS: 'Приседания',
            ChallengeType.PLANK: 'Планка',
            ChallengeType.RUNNING: 'Бег',
            ChallengeType.STEPS: 'Шаги'
        }
        return translations.get(challenge_type, challenge_type.value)

    def generate_event_participants_report(self, event_id: int) -> BytesIO:
        """Generate participants report for a specific event"""
        logger.info(f"Generating participants report for event {event_id}...")

        db = self.db_manager.get_session()
        try:
            from src.models.models import Event, EventRegistration

            # Get event details
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                raise ValueError(f"Event {event_id} not found")

            # Get participants registered for this event
            participants_data = db.query(
                Participant.id,
                Participant.full_name,
                Participant.birth_date,
                Participant.phone,
                Participant.start_number,
                Participant.distance_type,
                EventRegistration.registration_date
            ).join(EventRegistration, Participant.id == EventRegistration.participant_id).filter(
                EventRegistration.event_id == event_id
            ).all()

            # Convert to DataFrame
            df = pd.DataFrame(participants_data, columns=[
                'ID', 'ФИО', 'Дата рождения', 'Телефон', 'Стартовый номер',
                'Дистанция', 'Дата регистрации на событие'
            ])

            # Process data if there are participants
            if len(df) > 0:
                df['Дистанция'] = df['Дистанция'].map({
                    'adult_run': 'Взрослая',
                    'children_run': 'Детская'
                })

                df['Дата рождения'] = pd.to_datetime(df['Дата рождения']).dt.strftime('%d.%m.%Y')
                df['Дата регистрации на событие'] = pd.to_datetime(df['Дата регистрации на событие']).dt.strftime('%d.%m.%Y %H:%M')

            # Create Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Main sheet
                df.to_excel(writer, sheet_name='Участники', index=False)

                # Summary sheet
                summary_data = {
                    'Показатель': [
                        'Название события',
                        'Всего участников',
                        'Участников взрослой дистанции',
                        'Участников детской дистанции'
                    ],
                    'Значение': [
                        event.name,
                        len(df),
                        len(df[df['Дистанция'] == 'Взрослая']),
                        len(df[df['Дистанция'] == 'Детская'])
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Сводка', index=False)

            output.seek(0)
            logger.info(f"Event {event_id} participants report generated successfully")
            return output

        except Exception as e:
            logger.error(f"Error generating event participants report: {e}")
            raise
        finally:
            db.close()

    def generate_challenge_participants_report(self, challenge_id: int) -> BytesIO:
        """Generate participants report for a specific challenge"""
        logger.info(f"Generating participants report for challenge {challenge_id}...")

        db = self.db_manager.get_session()
        try:
            # Get challenge details
            challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
            if not challenge:
                raise ValueError(f"Challenge {challenge_id} not found")

            # Get participants who submitted reports for this challenge
            participants_data = db.query(
                Participant.id,
                Participant.full_name,
                Participant.birth_date,
                Participant.phone,
                Participant.start_number,
                Participant.distance_type
            ).join(Submission, Participant.id == Submission.participant_id).filter(
                Submission.challenge_id == challenge_id
            ).distinct().all()

            # Get submission statistics for each participant
            detailed_data = []
            participant_ids = [p.id for p in participants_data]
            submissions = []
            if participant_ids:
                submissions = db.query(Submission).filter(
                    Submission.participant_id.in_(participant_ids),
                    Submission.challenge_id == challenge_id
                ).all()

            submissions_by_participant = {}
            for s in submissions:
                submissions_by_participant.setdefault(s.participant_id, []).append(s)

            for participant in participants_data:
                participant_subs = submissions_by_participant.get(participant.id, [])
                total_submissions = len(participant_subs)
                approved_submissions = sum(1 for s in participant_subs if s.status == SubmissionStatus.APPROVED)
                best_result = max([s.result_value for s in participant_subs if s.result_value], default=0)

                detailed_data.append({
                    'ID': participant.id,
                    'ФИО': participant.full_name,
                    'Дата рождения': participant.birth_date,
                    'Телефон': participant.phone,
                    'Стартовый номер': participant.start_number,
                    'Дистанция': participant.distance_type,
                    'Всего отчётов': total_submissions,
                    'Одобренных': approved_submissions,
                    'Лучший результат': best_result
                })

            # Convert to DataFrame
            df = pd.DataFrame(detailed_data)

            # Process data if there are participants
            if len(df) > 0:
                df['Дистанция'] = df['Дистанция'].map({
                    'adult_run': 'Взрослая',
                    'children_run': 'Детская'
                })

                df['Дата рождения'] = pd.to_datetime(df['Дата рождения']).dt.strftime('%d.%m.%Y')

            # Create Excel file
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # Main sheet
                df.to_excel(writer, sheet_name='Участники', index=False)

                # Summary sheet
                summary_data = {
                    'Показатель': [
                        'Название челленджа',
                        'Тип челленджа',
                        'Всего участников',
                        'Всего отчётов',
                        'Одобренных отчётов',
                        'Средний лучший результат'
                    ],
                    'Значение': [
                        challenge.name,
                        self._translate_challenge_type(challenge.challenge_type),
                        len(df),
                        df['Всего отчётов'].sum(),
                        df['Одобренных'].sum(),
                        round(df['Лучший результат'].mean(), 2) if len(df) > 0 else 0
                    ]
                }
                summary_df = pd.DataFrame(summary_data)
                summary_df.to_excel(writer, sheet_name='Сводка', index=False)

            output.seek(0)
            logger.info(f"Challenge {challenge_id} participants report generated successfully")
            return output

        except Exception as e:
            logger.error(f"Error generating challenge participants report: {e}")
            raise
        finally:
            db.close()

    def generate_all_events_report(self) -> BytesIO:
        """Generate report with all events and their participants"""
        logger.info("Generating all events report...")

        db = self.db_manager.get_session()
        try:
            from src.models.models import Event, EventRegistration, EventType, EventStatus

            events = db.query(Event).filter(Event.is_active == True).order_by(Event.start_date.desc()).all()

            # Create Excel file with multiple sheets
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # If no events, create empty report
                if not events:
                    empty_df = pd.DataFrame(columns=[
                        'ID', 'Название', 'Тип', 'Дата начала', 'Статус',
                        'Всего участников', 'Взрослая дистанция', 'Детская дистанция'
                    ])
                    empty_df.to_excel(writer, sheet_name='Все события', index=False)
                    output.seek(0)
                    return output

                # Summary sheet with all events
                event_ids = [e.id for e in events]
                registration_rows = []
                if event_ids:
                    registration_rows = db.query(
                        EventRegistration.event_id,
                        Participant.distance_type
                    ).join(
                        Participant, EventRegistration.participant_id == Participant.id
                    ).filter(
                        EventRegistration.event_id.in_(event_ids)
                    ).all()

                counts = {}
                adult_counts = {}
                children_counts = {}
                for event_id, distance_type in registration_rows:
                    counts[event_id] = counts.get(event_id, 0) + 1
                    if distance_type == DistanceType.ADULT_RUN:
                        adult_counts[event_id] = adult_counts.get(event_id, 0) + 1
                    elif distance_type == DistanceType.CHILDREN_RUN:
                        children_counts[event_id] = children_counts.get(event_id, 0) + 1

                events_summary = []
                for event in events:
                    participant_count = counts.get(event.id, 0)
                    adult_count = adult_counts.get(event.id, 0)
                    children_count = children_counts.get(event.id, 0)

                    events_summary.append({
                        'ID': event.id,
                        'Название': event.name,
                        'Тип': 'Забег' if event.event_type == EventType.RUN_EVENT else 'Турнир',
                        'Дата начала': event.start_date.strftime('%d.%m.%Y') if event.start_date else '',
                        'Статус': self._translate_event_status(event.status),
                        'Всего участников': participant_count,
                        'Взрослая дистанция': adult_count,
                        'Детская дистанция': children_count
                    })

                summary_df = pd.DataFrame(events_summary)
                summary_df.to_excel(writer, sheet_name='Все события', index=False)

                # Individual sheets for each event (limit to first 10 events)
                top_events = events[:10]
                top_event_ids = [e.id for e in top_events]
                rows = []
                if top_event_ids:
                    rows = db.query(
                        EventRegistration.event_id,
                        Participant.full_name,
                        Participant.phone,
                        Participant.start_number,
                        Participant.distance_type,
                        EventRegistration.registration_date
                    ).join(Participant, Participant.id == EventRegistration.participant_id).filter(
                        EventRegistration.event_id.in_(top_event_ids)
                    ).all()

                by_event = {}
                for row in rows:
                    by_event.setdefault(row.event_id, []).append(row)

                for event in top_events:
                    participants_data = by_event.get(event.id, [])

                    if participants_data:
                        df = pd.DataFrame(participants_data, columns=[
                            'event_id', 'ФИО', 'Телефон', 'Стартовый номер', 'Дистанция', 'Дата регистрации'
                        ])
                        df = df.drop(columns=['event_id'])

                        df['Дистанция'] = df['Дистанция'].map({
                            'adult_run': 'Взрослая',
                            'children_run': 'Детская'
                        })

                        df['Дата регистрации'] = pd.to_datetime(df['Дата регистрации']).dt.strftime('%d.%m.%Y %H:%M')

                        # Truncate sheet name to 31 characters (Excel limit)
                        sheet_name = event.name[:28] + '...' if len(event.name) > 28 else event.name
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

            output.seek(0)
            logger.info("All events report generated successfully")
            return output

        except Exception as e:
            logger.error(f"Error generating all events report: {e}")
            raise
        finally:
            db.close()

    def generate_all_challenges_report(self) -> BytesIO:
        """Generate report with all challenges and their participants"""
        logger.info("Generating all challenges report...")

        db = self.db_manager.get_session()
        try:
            challenges = db.query(Challenge).filter(
                Challenge.is_active == True
            ).order_by(Challenge.end_date.desc()).all()

            # Create Excel file with multiple sheets
            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                # If no challenges, create empty report
                if not challenges:
                    empty_df = pd.DataFrame(columns=[
                        'ID', 'Название', 'Тип', 'Дата окончания',
                        'Участников', 'Всего отчётов', 'Одобрено'
                    ])
                    empty_df.to_excel(writer, sheet_name='Все челленджи', index=False)
                    output.seek(0)
                    return output

                # Summary sheet with all challenges
                challenges_summary = []
                for challenge in challenges:
                    participant_count = db.query(Participant.id).join(Submission).filter(
                        Submission.challenge_id == challenge.id
                    ).distinct().count()

                    total_submissions = db.query(Submission).filter(
                        Submission.challenge_id == challenge.id
                    ).count()

                    approved_submissions = db.query(Submission).filter(
                        Submission.challenge_id == challenge.id,
                        Submission.status == SubmissionStatus.APPROVED
                    ).count()

                    challenges_summary.append({
                        'ID': challenge.id,
                        'Название': challenge.name,
                        'Тип': self._translate_challenge_type(challenge.challenge_type),
                        'Дата окончания': challenge.end_date.strftime('%d.%m.%Y') if challenge.end_date else '',
                        'Участников': participant_count,
                        'Всего отчётов': total_submissions,
                        'Одобрено': approved_submissions
                    })

                summary_df = pd.DataFrame(challenges_summary)
                summary_df.to_excel(writer, sheet_name='Все челленджи', index=False)

                # Individual sheets for each challenge (limit to first 10 challenges)
                top_challenges = challenges[:10]
                top_ids = [c.id for c in top_challenges]
                rows = []
                if top_ids:
                    rows = db.query(
                        Submission.challenge_id,
                        Participant.id,
                        Participant.full_name,
                        Participant.phone,
                        Participant.start_number,
                        Participant.distance_type,
                        Submission.status,
                        Submission.result_value
                    ).join(Participant, Participant.id == Submission.participant_id).filter(
                        Submission.challenge_id.in_(top_ids)
                    ).all()

                by_challenge = {}
                for row in rows:
                    by_challenge.setdefault(row.challenge_id, []).append(row)

                for challenge in top_challenges:
                    rows_for_challenge = by_challenge.get(challenge.id, [])
                    if rows_for_challenge:
                        stats_by_participant = {}
                        for row in rows_for_challenge:
                            key = row.id
                            entry = stats_by_participant.setdefault(key, {
                                'ФИО': row.full_name,
                                'Телефон': row.phone,
                                'Стартовый номер': row.start_number,
                                'Дистанция': 'Взрослая' if row.distance_type == 'adult_run' else 'Детская',
                                'Отчётов': 0,
                                'Одобрено': 0,
                                'Лучший результат': 0
                            })
                            entry['Отчётов'] += 1
                            if row.status == SubmissionStatus.APPROVED:
                                entry['Одобрено'] += 1
                            if row.result_value and row.result_value > entry['Лучший результат']:
                                entry['Лучший результат'] = row.result_value

                        df = pd.DataFrame(list(stats_by_participant.values()))

                        # Truncate sheet name to 31 characters (Excel limit)
                        sheet_name = challenge.name[:28] + '...' if len(challenge.name) > 28 else challenge.name
                        df.to_excel(writer, sheet_name=sheet_name, index=False)

            output.seek(0)
            logger.info("All challenges report generated successfully")
            return output

        except Exception as e:
            logger.error(f"Error generating all challenges report: {e}")
            raise
        finally:
            db.close()

    def _translate_event_status(self, status) -> str:
        """Translate event status to Russian"""
        from src.models.models import EventStatus
        translations = {
            EventStatus.UPCOMING: 'Предстоящее',
            EventStatus.ACTIVE: 'Активное',
            EventStatus.FINISHED: 'Завершено',
            EventStatus.CANCELLED: 'Отменено'
        }
        return translations.get(status, str(status))
