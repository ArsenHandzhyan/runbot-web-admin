"""
Database models for RunBot
Defines all database tables and relationships
"""

from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, 
    ForeignKey, Float, Text, Enum, Date
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class DistanceType(enum.Enum):
    ADULT_RUN = "adult_run"
    CHILDREN_RUN = "children_run"

class ChallengeType(enum.Enum):
    PUSH_UPS = "push_ups"
    SQUATS = "squats"
    PLANK = "plank"
    RUNNING = "running"
    STEPS = "steps"

class SubmissionStatus(enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"

class AIAnalysisStatus(enum.Enum):
    QUEUED = "queued"           # В очереди на анализ
    PROCESSING = "processing"   # Обрабатывается
    COMPLETED = "completed"     # Успешно проанализировано
    FAILED = "failed"          # Ошибка анализа
    MANUAL_REQUIRED = "manual_required"  # Требуется ручная проверка

class EventType(enum.Enum):
    RUN_EVENT = "run_event"      # Забег
    CHALLENGE = "challenge"      # Челлендж
    TOURNAMENT = "tournament"    # Турнир

class EventStatus(enum.Enum):
    UPCOMING = "upcoming"        # Предстоит
    ACTIVE = "active"            # Активно
    FINISHED = "finished"        # Завершено
    CANCELLED = "cancelled"      # Отменено

class Participant(Base):
    """Participant model - stores registered users"""
    __tablename__ = 'participants'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)
    birth_date = Column(Date, nullable=False)
    phone = Column(String, nullable=False)
    distance_type = Column(Enum(DistanceType), nullable=True)
    start_number = Column(String, unique=True, nullable=False)
    registration_date = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    submissions = relationship("Submission", back_populates="participant")
    statistics = relationship("ParticipantStats", back_populates="participant")
    event_registrations = relationship("EventRegistration", back_populates="participant")

class Challenge(Base):
    """Challenge model - defines available challenges"""
    __tablename__ = 'challenges'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    challenge_type = Column(Enum(ChallengeType), nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    submissions = relationship("Submission", back_populates="challenge")

class Submission(Base):
    """Submission model - stores participant submissions"""
    __tablename__ = 'submissions'
    
    id = Column(Integer, primary_key=True)
    participant_id = Column(Integer, ForeignKey('participants.id'), nullable=False)
    challenge_id = Column(Integer, ForeignKey('challenges.id', ondelete='CASCADE'), nullable=False)
    submission_date = Column(DateTime, default=datetime.utcnow)
    media_path = Column(String)  # Path to uploaded media
    result_value = Column(Float)  # Numeric result (reps, seconds, km, etc.)
    result_unit = Column(String)  # Unit of measurement
    comment = Column(Text)  # Optional text comment
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.PENDING)
    moderator_comment = Column(Text)  # Moderator's feedback
    
    # Relationships
    participant = relationship("Participant", back_populates="submissions")
    challenge = relationship("Challenge", back_populates="submissions")
    ai_analysis = relationship("AIAnalysis", back_populates="submission", uselist=False)

class AIAnalysis(Base):
    """AI video analysis results"""
    __tablename__ = 'ai_analysis'

    id = Column(Integer, primary_key=True)
    submission_id = Column(Integer, ForeignKey('submissions.id'), nullable=False, unique=True)

    # Статус анализа
    status = Column(Enum(AIAnalysisStatus), default=AIAnalysisStatus.QUEUED)

    # Результаты AI
    detected_exercise = Column(String)  # "push_ups", "squats", "plank"
    detected_reps = Column(Integer)     # Количество повторений
    confidence = Column(Float)          # 0.0 - 1.0
    duration_sec = Column(Float)        # Длительность видео

    # Детали анализа
    frames_analyzed = Column(Integer)   # Сколько кадров проанализировано
    frames_with_pose = Column(Integer)  # В скольких найдена поза
    pose_detection_rate = Column(Float) # frames_with_pose / frames_analyzed

    # Флаги качества
    manual_review_required = Column(Boolean, default=False)
    quality_issues = Column(Text)       # JSON список проблем

    # Технические данные
    processing_time_sec = Column(Float)
    error_message = Column(Text)

    # Метаданные
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    submission = relationship("Submission", back_populates="ai_analysis")

class AIWorkerSettings(Base):
    """AI worker settings stored in DB (single row)"""
    __tablename__ = "ai_worker_settings"

    id = Column(Integer, primary_key=True)

    min_confidence = Column(Float, default=0.75)
    min_pose_detection_rate = Column(Float, default=0.7)
    min_video_duration = Column(Integer, default=8)
    frame_skip = Column(Integer, default=1)
    pose_visibility_min = Column(Float, default=0.5)
    angle_smoothing_alpha = Column(Float, default=0.2)
    phase_debounce_frames = Column(Integer, default=3)
    pushup_down_threshold = Column(Float, default=90)
    pushup_up_threshold = Column(Float, default=160)
    squat_down_threshold = Column(Float, default=90)
    squat_up_threshold = Column(Float, default=165)
    mediapipe_min_detection_confidence = Column(Float, default=0.5)
    mediapipe_min_tracking_confidence = Column(Float, default=0.5)
    max_processing_time = Column(Integer, default=300)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class ParticipantStats(Base):
    """Statistics model - calculated participant statistics"""
    __tablename__ = 'participant_stats'
    
    id = Column(Integer, primary_key=True)
    participant_id = Column(Integer, ForeignKey('participants.id'), nullable=False)
    challenge_id = Column(Integer, ForeignKey('challenges.id'))
    total_submissions = Column(Integer, default=0)
    approved_submissions = Column(Integer, default=0)
    total_score = Column(Float, default=0.0)
    average_score = Column(Float, default=0.0)
    streak_days = Column(Integer, default=0)  # Consecutive days
    last_submission_date = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    participant = relationship("Participant", back_populates="statistics")

class Admin(Base):
    """Admin model - manages bot administrators"""
    __tablename__ = 'admins'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(String, unique=True, nullable=False)
    username = Column(String)
    full_name = Column(String)
    added_by = Column(String)  # Who added this admin
    added_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    def __repr__(self):
        return f"<Admin(telegram_id='{self.telegram_id}', username='{self.username}')>"


class AdminAction(Base):
    """Admin action log - tracks admin activities"""
    __tablename__ = 'admin_actions'
    
    id = Column(Integer, primary_key=True)
    admin_telegram_id = Column(String, nullable=False)
    action_type = Column(String, nullable=False)  # approve, reject, export, etc.
    target_id = Column(Integer)  # ID of affected record
    details = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

# Новые модели для системы событий

class Event(Base):
    """Event model - defines all types of events (runs, challenges, tournaments)"""
    __tablename__ = 'events'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    description = Column(Text)
    event_type = Column(Enum(EventType), nullable=False)
    # For run events - distance type
    distance_type = Column(Enum(DistanceType))
    # For challenges - challenge type  
    challenge_type = Column(Enum(ChallengeType))
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    registration_deadline = Column(DateTime)
    max_participants = Column(Integer)  # Optional limit
    is_active = Column(Boolean, default=True)
    status = Column(Enum(EventStatus), default=EventStatus.UPCOMING)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    registrations = relationship(
        "EventRegistration", back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )

class EventRegistration(Base):
    """Event registration model - tracks participant registrations for events"""
    __tablename__ = 'event_registrations'
    
    id = Column(Integer, primary_key=True)
    participant_id = Column(Integer, ForeignKey('participants.id'), nullable=False)
    event_id = Column(Integer, ForeignKey('events.id', ondelete='CASCADE'), nullable=False)
    registration_date = Column(DateTime, default=datetime.utcnow)
    registration_status = Column(Enum(SubmissionStatus), default=SubmissionStatus.APPROVED)
    bib_number = Column(String)  # Unique number for this event
    # Additional event-specific data
    team_name = Column(String)   # For team events
    category = Column(String)    # Age/gender category
    
    # Relationships
    participant = relationship("Participant", back_populates="event_registrations")
    event = relationship("Event", back_populates="registrations")
    submissions = relationship("EventSubmission", back_populates="registration")

class EventSubmission(Base):
    """Event submission model - stores submissions for specific events"""
    __tablename__ = 'event_submissions'
    
    id = Column(Integer, primary_key=True)
    registration_id = Column(Integer, ForeignKey('event_registrations.id'), nullable=False)
    submission_date = Column(DateTime, default=datetime.utcnow)
    media_path = Column(String)
    result_value = Column(Float)
    result_unit = Column(String)
    comment = Column(Text)
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.PENDING)
    moderator_comment = Column(Text)
    
    # Relationships
    registration = relationship("EventRegistration", back_populates="submissions")

# Модель регистрации на челленджи

class ChallengeRegistration(Base):
    """Challenge registration model - tracks participant registrations for challenges"""
    __tablename__ = 'challenge_registrations'
    
    id = Column(Integer, primary_key=True)
    participant_id = Column(Integer, ForeignKey('participants.id'), nullable=False)
    challenge_id = Column(Integer, ForeignKey('challenges.id'), nullable=False)
    registration_date = Column(DateTime, default=datetime.utcnow)
    bib_number = Column(String)  # Unique number for this challenge
    is_active = Column(Boolean, default=True)
    
    # Relationships
    participant = relationship("Participant", back_populates="challenge_registrations")
    challenge = relationship("Challenge", back_populates="registrations")

# Добавим relationship в существующие модели
Participant.challenge_registrations = relationship(
    "ChallengeRegistration", back_populates="participant", cascade="all, delete-orphan", passive_deletes=True
)
Challenge.registrations = relationship(
    "ChallengeRegistration", back_populates="challenge", cascade="all, delete-orphan", passive_deletes=True
)
