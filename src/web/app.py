"""
Web Admin Interface for RunBot
Simple Flask-based admin panel for managing events, challenges and participants
"""

import hashlib
import logging
import os
import time
from collections import defaultdict
import json
from datetime import datetime, timedelta
from functools import wraps

import requests
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from sqlalchemy import func, text
from sqlalchemy.orm import selectinload

# Removed problematic import: from src.web.test_media import test_media_blueprint
# This import was causing deployment failures on Render.com

from src.database.db import DatabaseManager
from src.models.models import Participant, Event, Challenge, ChallengeType, Submission, SubmissionStatus, Admin, EventType, EventStatus, ChallengeRegistration, AIAnalysis, AIAnalysisStatus, AIWorkerSettings, AITestResult
from src.utils.event_manager import EventManager
from src.utils.challenge_manager import ChallengeManager
# NOTE: telebot import removed - web interface doesn't need bot functionality

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Simple in-memory TTL cache (per process)
_cache = {}


def _cache_get(key):
    item = _cache.get(key)
    if not item:
        return None
    if time.time() - item['ts'] > item['ttl']:
        _cache.pop(key, None)
        return None
    return item['value']


def _cache_set(key, value, ttl):
    _cache[key] = {'value': value, 'ttl': ttl, 'ts': time.time()}

# Runtime tuning (env overrides, safe defaults)
LOGIN_MAX_ATTEMPTS = int(os.getenv('LOGIN_MAX_ATTEMPTS', '5'))
LOGIN_WINDOW_SECONDS = int(os.getenv('LOGIN_WINDOW_SECONDS', '300'))
LOGIN_LOCKOUT_SECONDS = int(os.getenv('LOGIN_LOCKOUT_SECONDS', '900'))
MODERATION_ALL_LIMIT = int(os.getenv('MODERATION_ALL_LIMIT', '50'))
MODERATION_PENDING_LIMIT = int(os.getenv('MODERATION_PENDING_LIMIT', '0'))  # 0 = no limit
DASHBOARD_RECENT_LIMIT = int(os.getenv('DASHBOARD_RECENT_LIMIT', '5'))
PARTICIPANTS_PER_PAGE = int(os.getenv('PARTICIPANTS_PER_PAGE', '50'))
PARTICIPANTS_CACHE_TTL_SECONDS = int(os.getenv('PARTICIPANTS_CACHE_TTL_SECONDS', '30'))
STATISTICS_CACHE_TTL_SECONDS = int(os.getenv('STATISTICS_CACHE_TTL_SECONDS', '30'))
# Rate limiting для защиты от brute-force атак
class RateLimiter:
    """Simple in-memory rate limiter for login attempts"""
    def __init__(self, max_attempts=5, window_seconds=300, lockout_seconds=900):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self.attempts = defaultdict(list)  # IP -> list of timestamps
        self.lockouts = {}  # IP -> lockout_until timestamp

    def _get_client_ip(self, request):
        """Get client IP, accounting for proxies"""
        if request.headers.get('X-Forwarded-For'):
            return request.headers.get('X-Forwarded-For').split(',')[0].strip()
        return request.remote_addr or 'unknown'

    def is_locked_out(self, request):
        """Check if IP is currently locked out"""
        ip = self._get_client_ip(request)
        if ip in self.lockouts:
            if time.time() < self.lockouts[ip]:
                return True
            else:
                del self.lockouts[ip]
        return False

    def record_attempt(self, request, success=False):
        """Record a login attempt"""
        ip = self._get_client_ip(request)
        now = time.time()

        if success:
            # Clear attempts on successful login
            self.attempts[ip] = []
            if ip in self.lockouts:
                del self.lockouts[ip]
            return

        # Clean old attempts
        self.attempts[ip] = [t for t in self.attempts[ip] if now - t < self.window_seconds]

        # Record new attempt
        self.attempts[ip].append(now)

        # Check if we need to lockout
        if len(self.attempts[ip]) >= self.max_attempts:
            self.lockouts[ip] = now + self.lockout_seconds
            logger.warning(f"IP {ip} locked out after {self.max_attempts} failed login attempts")

    def get_remaining_lockout(self, request):
        """Get remaining lockout time in seconds"""
        ip = self._get_client_ip(request)
        if ip in self.lockouts:
            remaining = self.lockouts[ip] - time.time()
            return max(0, int(remaining))
        return 0

# Global rate limiter instance
login_rate_limiter = RateLimiter(
    max_attempts=LOGIN_MAX_ATTEMPTS,
    window_seconds=LOGIN_WINDOW_SECONDS,
    lockout_seconds=LOGIN_LOCKOUT_SECONDS
)

def create_app():
    # Get the project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    app = Flask(__name__,
                template_folder=os.path.join(project_root, 'templates'),
                static_folder=os.path.join(project_root, 'static'))

    # Секретный ключ - ОБЯЗАТЕЛЬНО из переменной окружения
    secret_key = os.getenv('WEB_SECRET_KEY')
    if not secret_key:
        logger.warning("WEB_SECRET_KEY not set! Using fallback (NOT SECURE FOR PRODUCTION)")
        secret_key = 'dev-only-change-in-production-' + str(hash(os.urandom(16)))
    app.secret_key = secret_key

    # CSRF Protection
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 час

    # Secure session cookies
    secure_env = os.getenv('SESSION_COOKIE_SECURE')
    if secure_env is not None:
        app.config['SESSION_COOKIE_SECURE'] = secure_env.lower() in ('1', 'true', 'yes')
    else:
        app.config['SESSION_COOKIE_SECURE'] = os.getenv('FLASK_ENV') == 'production'
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
    session_minutes = int(os.getenv('SESSION_LIFETIME_MINUTES', '480'))
    app.permanent_session_lifetime = timedelta(minutes=session_minutes)

    # НЕ логируем DATABASE_URL - содержит пароль!
    logger.info("Database connection configured")

    # Initialize CSRF protection
    try:
        from flask_wtf.csrf import CSRFProtect
        csrf = CSRFProtect(app)
        logger.info("CSRF protection enabled")
    except ImportError:
        logger.warning("Flask-WTF not installed, CSRF protection disabled")
        csrf = None

    # Initialize managers
    # Security headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        return response

    db_manager = DatabaseManager()
    # NOTE: Web interface doesn't need bot instance - only database access
    # bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))  # REMOVED - causes conflicts
    # event_manager = EventManager(bot, db_manager)  # REMOVED
    # challenge_manager = ChallengeManager(bot, db_manager)  # REMOVED
    
    # Function to translate challenge types to Russian
    def translate_challenge_type(challenge_type):
        """Translate challenge type enum to Russian"""
        translations = {
            'PUSH_UPS': 'Отжимания',
            'SQUATS': 'Приседания',
            'PLANK': 'Планка',
            'RUNNING': 'Бег',
            'STEPS': 'Шаги'
        }
        return translations.get(challenge_type.name, challenge_type.value)
    
    # Make function available in templates
    app.jinja_env.globals.update(translate_challenge_type=translate_challenge_type)
    
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'admin_logged_in' not in session:
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function
    
    @app.route('/')
    @login_required
    def index():
        """Main dashboard"""
        db = db_manager.get_session()
        response_error = None
        try:
            cache_ttl = int(os.getenv('DASHBOARD_CACHE_TTL_SECONDS', '30'))
            cached = _cache_get('dashboard')
            if cached:
                return render_template('dashboard.html', **cached)

            # Get counts for dashboard
            participants_count = db.query(Participant).filter(Participant.is_active == True).count()
            events_count = db.query(Event).filter(Event.is_active == True).count()
            challenges_count = db.query(Challenge).filter(Challenge.is_active == True).count()
            submissions_count = db.query(Submission).count()
            pending_submissions_count = db.query(Submission).filter(
                Submission.status == SubmissionStatus.PENDING
            ).count()

            # Get recent activity
            recent_events = db.query(Event).filter(Event.is_active == True).order_by(Event.created_at.desc()).limit(DASHBOARD_RECENT_LIMIT).all()
            recent_challenges = db.query(Challenge).filter(Challenge.is_active == True).order_by(Challenge.created_at.desc()).limit(DASHBOARD_RECENT_LIMIT).all()

            context = {
                'participants_count': participants_count,
                'events_count': events_count,
                'challenges_count': challenges_count,
                'submissions_count': submissions_count,
                'pending_submissions_count': pending_submissions_count,
                'recent_events': recent_events,
                'recent_challenges': recent_challenges
            }
            _cache_set('dashboard', context, cache_ttl)

            return render_template('dashboard.html', **context)
        finally:
            db.close()
    
    @app.route('/media/<path:filename>')
    @login_required
    def serve_media(filename):
        """Serve media files from media directory or redirect to R2"""
        logger.debug("serve_media: received filename=%s", filename)
        logger.debug("serve_media: starts with https://? %s", filename.startswith('https://'))
        logger.debug("serve_media: length of filename: %d", len(filename))

        # Clean filename - remove any leading path components
        if '/' in filename:
            filename = filename.split('/')[-1]
            logger.debug("serve_media: cleaned filename to: %s", filename)

        # Check if filename is an R2 URL (starts with https://)
        if filename.startswith('https://'):
            logger.debug("serve_media: REDIRECTING to R2 URL: %s", filename)
            return redirect(filename)
        else:
            logger.debug("serve_media: SERVING LOCALLY - filename does not start with https://")

        # Compute project root reliably and serve media from there
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        media_path = os.path.join(repo_root, 'media')
        file_path = os.path.join(media_path, filename)
        logger.debug("serve_media: filename=%s, media_path=%s, exists=%s", filename, media_path, os.path.exists(file_path))

        try:
            return send_from_directory(media_path, filename)
        except Exception as e:
            logger.exception("serve_media error: %s", e)
            raise

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Admin login with rate limiting protection"""
        if os.getenv("DISABLE_LOGIN", "false").lower() in ("1", "true", "yes"):
            session['admin_logged_in'] = True
            session.permanent = True
            return redirect(url_for('index'))
        # Check if IP is locked out
        if login_rate_limiter.is_locked_out(request):
            remaining = login_rate_limiter.get_remaining_lockout(request)
            flash(f'Слишком много неудачных попыток. Попробуйте через {remaining // 60} мин.', 'error')
            logger.warning(f"Blocked login attempt from locked out IP")
            return render_template('login.html'), 429

        if request.method == 'POST':
            username = request.form.get('username', '')
            password = request.form.get('password', '')

            # Получить учётные данные из переменных окружения (без дефолтов для безопасности)
            admin_username = os.getenv('ADMIN_USERNAME')
            admin_password = os.getenv('ADMIN_PASSWORD')

            if not admin_username or not admin_password:
                logger.error("ADMIN_USERNAME or ADMIN_PASSWORD not configured!")
                flash('Ошибка конфигурации сервера', 'error')
                return render_template('login.html'), 500

            # Constant-time comparison to prevent timing attacks
            username_match = hashlib.sha256(username.encode()).hexdigest() == hashlib.sha256(admin_username.encode()).hexdigest()
            password_match = hashlib.sha256(password.encode()).hexdigest() == hashlib.sha256(admin_password.encode()).hexdigest()

            if username_match and password_match:
                login_rate_limiter.record_attempt(request, success=True)
                session['admin_logged_in'] = True
                session['admin_username'] = username
                logger.info(f"Successful login for user: {username}")
                flash('Успешный вход в систему!', 'success')
                return redirect(url_for('index'))
            else:
                login_rate_limiter.record_attempt(request, success=False)
                logger.warning(f"Failed login attempt for username: {username}")
                flash('Неверное имя пользователя или пароль', 'error')

        return render_template('login.html')
    
    @app.route('/logout')
    def logout():
        """Admin logout"""
        session.clear()
        flash('Вы вышли из системы', 'info')
        return redirect(url_for('login'))
    
    @app.route('/events')
    @login_required
    def events():
        """Manage events"""
        db = db_manager.get_session()
        try:
            events_list = db.query(Event).order_by(Event.created_at.desc()).all()

            # Add status information to each event
            now = datetime.now()
            for event in events_list:
                # Calculate event status
                if event.status == EventStatus.CANCELLED:
                    event.status_text = "Отменен"
                    event.status_class = "danger"
                elif now < event.start_date:
                    # Event hasn't started yet
                    delta = event.start_date - now
                    days = delta.days
                    hours = delta.seconds // 3600

                    if days > 0:
                        event.status_text = f"Начало через {days} дн."
                    elif hours > 0:
                        event.status_text = f"Начало через {hours} ч."
                    else:
                        minutes = delta.seconds // 60
                        event.status_text = f"Начало через {minutes} мин."
                    event.status_class = "warning"
                elif now > event.end_date:
                    # Event has ended
                    event.status_text = "Завершен"
                    event.status_class = "info"
                else:
                    # Event is active now
                    delta = event.end_date - now
                    days = delta.days
                    hours = delta.seconds // 3600

                    if days > 0:
                        event.status_text = f"Активен ({days} дн. осталось)"
                    elif hours > 0:
                        event.status_text = f"Активен ({hours} ч. осталось)"
                    else:
                        minutes = delta.seconds // 60
                        event.status_text = f"Активен ({minutes} мин. осталось)"
                    event.status_class = "success"

            return render_template('events.html', events=events_list)
        finally:
            db.close()
    
    @app.route('/events/create', methods=['GET', 'POST'])
    @login_required
    def create_event():
        """Create new event"""
        if request.method == 'POST':
            try:
                name = request.form['name']
                description = request.form['description']
                event_type = request.form['event_type']
                start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M')
                end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M')
                registration_deadline = datetime.strptime(request.form['registration_deadline'], '%Y-%m-%dT%H:%M')
                max_participants = int(request.form['max_participants']) if request.form['max_participants'] else None
                
                db = db_manager.get_session()
                try:
                    new_event = Event(
                        name=name,
                        description=description,
                        event_type=EventType[event_type],
                        start_date=start_date,
                        end_date=end_date,
                        registration_deadline=registration_deadline,
                        max_participants=max_participants,
                        is_active=True
                    )
                    db.add(new_event)
                    db.commit()
                    flash('Событие успешно создано!', 'success')
                    return redirect(url_for('events'))
                finally:
                    db.close()
            except Exception as e:
                flash(f'Ошибка при создании события: {str(e)}', 'error')
        
        return render_template('create_event.html', EventType=EventType)
    
    @app.route('/events/<int:event_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_event(event_id):
        """Edit existing event"""
        db = db_manager.get_session()
        try:
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                flash('Событие не найдено', 'error')
                return redirect(url_for('events'))
            
            if request.method == 'POST':
                try:
                    event.name = request.form['name']
                    event.description = request.form['description']
                    event.event_type = EventType[request.form['event_type']]
                    event.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M')
                    event.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M')
                    event.registration_deadline = datetime.strptime(request.form['registration_deadline'], '%Y-%m-%dT%H:%M')
                    event.max_participants = int(request.form['max_participants']) if request.form['max_participants'] else None
                    event.is_active = 'is_active' in request.form
                    
                    db.commit()
                    flash('Событие успешно обновлено!', 'success')
                    return redirect(url_for('events'))
                except Exception as e:
                    flash(f'Ошибка при обновлении события: {str(e)}', 'error')
            
            return render_template('edit_event.html', event=event, EventType=EventType)
        finally:
            db.close()
    
    @app.route('/events/<int:event_id>/delete', methods=['POST'])
    @login_required
    def delete_event(event_id):
        """Delete event (registrations will be cascaded and deleted)"""
        db = db_manager.get_session()
        try:
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                flash('Событие не найдено', 'error')
                return redirect(url_for('events'))
            
            # Allow cascade delete of related registrations via ON DELETE CASCADE
            db.delete(event)
            db.commit()
            flash('Событие успешно удалено!', 'success')
        except Exception as e:
            flash(f'Ошибка при удалении события: {str(e)}', 'error')
        finally:
            db.close()
        
        return redirect(url_for('events'))
    
    @app.route('/challenges')
    @login_required
    def challenges():
        """Manage challenges"""
        from sqlalchemy import func
        db = db_manager.get_session()
        try:
            # ОПТИМИЗАЦИЯ: Получить все челленджи с подсчётами за один запрос вместо N+1
            # Subquery для подсчёта участников
            participant_counts = db.query(
                ChallengeRegistration.challenge_id,
                func.count(ChallengeRegistration.id).label('participant_count')
            ).filter(
                ChallengeRegistration.is_active == True
            ).group_by(ChallengeRegistration.challenge_id).subquery()

            # Subquery для подсчёта отправок
            submission_counts = db.query(
                Submission.challenge_id,
                func.count(Submission.id).label('submission_count')
            ).group_by(Submission.challenge_id).subquery()

            # Основной запрос с LEFT JOIN
            challenges_list = db.query(
                Challenge,
                func.coalesce(participant_counts.c.participant_count, 0).label('participant_count'),
                func.coalesce(submission_counts.c.submission_count, 0).label('submission_count')
            ).outerjoin(
                participant_counts, Challenge.id == participant_counts.c.challenge_id
            ).outerjoin(
                submission_counts, Challenge.id == submission_counts.c.challenge_id
            ).order_by(Challenge.created_at.desc()).all()

            # Add participant and submission counts to each challenge
            challenges_with_counts = []
            now = datetime.now()

            for challenge, participant_count, submission_count in challenges_list:

                # Calculate challenge status
                if not challenge.is_active:
                    status_text = "Неактивен"
                    status_class = "secondary"
                elif now < challenge.start_date:
                    # Challenge hasn't started yet
                    delta = challenge.start_date - now
                    days = delta.days
                    hours = delta.seconds // 3600

                    if days > 0:
                        status_text = f"Начало через {days} дн."
                    elif hours > 0:
                        status_text = f"Начало через {hours} ч."
                    else:
                        minutes = delta.seconds // 60
                        status_text = f"Начало через {minutes} мин."
                    status_class = "warning"
                elif now > challenge.end_date:
                    # Challenge has ended
                    status_text = "Завершен"
                    status_class = "danger"
                else:
                    # Challenge is active now
                    delta = challenge.end_date - now
                    days = delta.days
                    hours = delta.seconds // 3600

                    if days > 0:
                        status_text = f"Активен ({days} дн. осталось)"
                    elif hours > 0:
                        status_text = f"Активен ({hours} ч. осталось)"
                    else:
                        minutes = delta.seconds // 60
                        status_text = f"Активен ({minutes} мин. осталось)"
                    status_class = "success"

                # Add counts and status to challenge object
                challenge.participant_count = participant_count
                challenge.submission_count = submission_count
                challenge.status_text = status_text
                challenge.status_class = status_class
                challenges_with_counts.append(challenge)

            return render_template('challenges.html',
                                 challenges=challenges_with_counts,
                                 ChallengeType=ChallengeType)
        finally:
            db.close()
    
    @app.route('/challenges/create', methods=['GET', 'POST'])
    @login_required
    def create_challenge():
        """Create new challenge"""
        if request.method == 'POST':
            try:
                name = request.form['name']
                description = request.form['description']
                challenge_type = request.form['challenge_type']
                target_value = float(request.form['target_value'])
                unit = request.form['unit']
                start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M')
                end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M')
                
                db = db_manager.get_session()
                try:
                    new_challenge = Challenge(
                        name=name,
                        description=description,
                        challenge_type=ChallengeType[challenge_type],
                        target_value=target_value,
                        unit=unit,
                        start_date=start_date,
                        end_date=end_date,
                        is_active=True
                    )
                    db.add(new_challenge)
                    db.commit()
                    flash('Челлендж успешно создан!', 'success')
                    return redirect(url_for('challenges'))
                finally:
                    db.close()
            except Exception as e:
                flash(f'Ошибка при создании челленджа: {str(e)}', 'error')
        
        return render_template('create_challenge.html', ChallengeType=ChallengeType)
    
    @app.route('/challenges/<int:challenge_id>/edit', methods=['GET', 'POST'])
    @login_required
    def edit_challenge(challenge_id):
        """Edit existing challenge"""
        db = db_manager.get_session()
        try:
            challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
            if not challenge:
                flash('Челлендж не найден', 'error')
                return redirect(url_for('challenges'))
            
            if request.method == 'POST':
                try:
                    challenge.name = request.form['name']
                    challenge.description = request.form['description']
                    challenge.challenge_type = ChallengeType[request.form['challenge_type']]
                    challenge.target_value = float(request.form['target_value'])
                    challenge.unit = request.form['unit']
                    challenge.start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%dT%H:%M')
                    challenge.end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%dT%H:%M')
                    challenge.is_active = 'is_active' in request.form
                    
                    db.commit()
                    flash('Челлендж успешно обновлен!', 'success')
                    return redirect(url_for('challenges'))
                except Exception as e:
                    flash(f'Ошибка при обновлении челленджа: {str(e)}', 'error')
            
            return render_template('edit_challenge.html', challenge=challenge, ChallengeType=ChallengeType)
        finally:
            db.close()
    
    @app.route('/challenges/<int:challenge_id>/delete', methods=['POST'])
    @login_required
    def delete_challenge(challenge_id):
        """Delete challenge"""
        db = db_manager.get_session()
        try:
            challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
            if not challenge:
                flash('Челлендж не найден', 'error')
                return redirect(url_for('challenges'))
            
            # Pre-clean related challenge registrations to avoid FK NULL violations
            try:
                db.query(ChallengeRegistration).filter(
                    ChallengeRegistration.challenge_id == challenge_id
                ).delete(synchronize_session=False)
                db.commit()
            except Exception as e:
                flash(f'Ошибка при удалении связанных регистрации челленджa: {str(e)}', 'error')
                return redirect(url_for('challenges'))

            # Check if challenge has submissions
            if challenge.submissions:
                flash('Нельзя удалить челлендж с отчетами', 'error')
                return redirect(url_for('challenges'))
            
            db.delete(challenge)
            db.commit()
            flash('Челлендж успешно удален!', 'success')
        except Exception as e:
            flash(f'Ошибка при удалении челленджа: {str(e)}', 'error')
        finally:
            db.close()
        
        return redirect(url_for('challenges'))
    
    @app.route('/challenges/<int:challenge_id>/submissions')
    @login_required
    def challenge_submissions(challenge_id):
        """View submissions for specific challenge"""
        db = db_manager.get_session()
        try:
            challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
            if not challenge:
                flash('Челлендж не найден', 'error')
                return redirect(url_for('challenges'))
            
            # Get all submissions for this challenge
            submissions = db.query(Submission).options(
                selectinload(Submission.participant),
                selectinload(Submission.ai_analysis)
            ).filter(
                Submission.challenge_id == challenge_id
            ).order_by(Submission.submission_date.desc()).all()
            
            # Get participant info for each submission and prepare data for template
            submissions_with_participants = []
            for submission in submissions:
                participant = submission.participant
                
                # Convert enum status to lowercase string for template comparison
                # Handle different enum representations
                if hasattr(submission.status, 'value'):
                    # Standard enum with value attribute
                    status_value = submission.status.value.lower()
                elif hasattr(submission.status, 'name'):
                    # Enum with name attribute
                    status_value = submission.status.name.lower()
                else:
                    # Fallback - convert to string and extract
                    status_str = str(submission.status)
                    if '.' in status_str:
                        # Handle 'SubmissionStatus.APPROVED' format
                        status_value = status_str.split('.')[-1].lower()
                    else:
                        status_value = status_str.lower()
                
                submissions_with_participants.append({
                    'submission': submission,
                    'participant': participant,
                    'status_value': status_value,
                    'ai_analysis': submission.ai_analysis
                })
            
            return render_template('challenge_submissions.html', 
                                 challenge=challenge,
                                 submissions=submissions_with_participants,
                                 SubmissionStatus=SubmissionStatus)
        finally:
            db.close()
    
    @app.route('/moderation')
    @login_required
    def moderation():
        """View pending submissions for moderation"""
        db = db_manager.get_session()
        try:
            try:
                # Get pending submissions
                pending_query = db.query(Submission).options(
                    selectinload(Submission.participant),
                    selectinload(Submission.challenge),
                    selectinload(Submission.ai_analysis)
                ).filter(
                    Submission.status == SubmissionStatus.PENDING
                ).order_by(Submission.submission_date.asc())
                if MODERATION_PENDING_LIMIT > 0:
                    pending_query = pending_query.limit(MODERATION_PENDING_LIMIT)
                pending_submissions = pending_query.all()

                # Get all submissions (for overview)
                all_submissions = db.query(Submission).options(
                    selectinload(Submission.participant),
                    selectinload(Submission.challenge),
                    selectinload(Submission.ai_analysis)
                ).order_by(Submission.submission_date.desc()).limit(MODERATION_ALL_LIMIT).all()
            except Exception as e:
                # Log and render with empty data to avoid 500 on UI
                logger.exception("Ошибка при загрузке данных модерации: %s", e)
                pending_submissions = []
                all_submissions = []

            # Prepare data for templates
            pending_with_details = []
            all_with_details = []

            for submission in pending_submissions:
                participant = submission.participant
                challenge = submission.challenge

                pending_with_details.append({
                    'submission': submission,
                    'participant': participant,
                    'challenge': challenge,
                    'ai_analysis': submission.ai_analysis
                })

            for submission in all_submissions:
                participant = submission.participant
                challenge = submission.challenge

                # Convert status for template
                if hasattr(submission.status, 'value'):
                    status_value = submission.status.value.lower()
                elif hasattr(submission.status, 'name'):
                    status_value = submission.status.name.lower()
                else:
                    status_str = str(submission.status)
                    if '.' in status_str:
                        status_value = status_str.split('.')[-1].lower()
                    else:
                        status_value = status_str.lower()

                all_with_details.append({
                    'submission': submission,
                    'participant': participant,
                    'challenge': challenge,
                    'status_value': status_value,
                    'ai_analysis': submission.ai_analysis
                })

            return render_template('moderation.html',
                                 pending_submissions=pending_with_details,
                                 all_submissions=all_with_details,
                                 SubmissionStatus=SubmissionStatus)
        except Exception as e:
            # Final fallback: log and show a user-friendly error on the page
            logger.exception("Unhandled error on moderation page: %s", e)
            flash('Ошибка загрузки модерации. Попробуйте позже.', 'error')
            return render_template('moderation.html',
                                   pending_submissions=[],
                                   all_submissions=[],
                                   SubmissionStatus=SubmissionStatus)
        finally:
            db.close()
    
    @app.route('/moderation/approve/<int:submission_id>', methods=['POST'])
    @login_required
    def approve_submission(submission_id):
        """Approve a submission"""
        try:
            db = db_manager.get_session()
            try:
                submission = db.query(Submission).get(submission_id)
                if not submission:
                    flash('Отчет не найден', 'error')
                    return redirect(url_for('moderation'))
                
                submission.status = SubmissionStatus.APPROVED
                submission.moderator_comment = request.form.get('comment', '')
                db.commit()
                
                flash('Отчет успешно одобрен!', 'success')
            finally:
                db.close()
        except Exception as e:
            flash(f'Ошибка при одобрении отчета: {str(e)}', 'error')
        
        return redirect(url_for('moderation'))
    
    @app.route('/moderation/reject/<int:submission_id>', methods=['POST'])
    @login_required
    def reject_submission(submission_id):
        """Reject a submission"""
        try:
            db = db_manager.get_session()
            try:
                submission = db.query(Submission).get(submission_id)
                if not submission:
                    flash('Отчет не найден', 'error')
                    return redirect(url_for('moderation'))
                
                submission.status = SubmissionStatus.REJECTED
                submission.moderator_comment = request.form.get('comment', '')
                db.commit()
                
                flash('Отчет успешно отклонен!', 'success')
            finally:
                db.close()
        except Exception as e:
            flash(f'Ошибка при отклонении отчета: {str(e)}', 'error')
        
        return redirect(url_for('moderation'))
    
    @app.route('/submissions/<int:submission_id>/media')
    @login_required
    def view_submission_media(submission_id):
        """View media attached to a submission"""
        db = db_manager.get_session()
        try:
            submission = db.query(Submission).get(submission_id)
            if not submission:
                flash('Отчет не найден', 'error')
                return redirect(url_for('moderation'))
            
            participant = db.query(Participant).filter(
                Participant.id == submission.participant_id
            ).first()
            
            challenge = db.query(Challenge).filter(
                Challenge.id == submission.challenge_id
            ).first()
            
            # Convert status for template
            if hasattr(submission.status, 'value'):
                status_value = submission.status.value.lower()
            elif hasattr(submission.status, 'name'):
                status_value = submission.status.name.lower()
            else:
                status_str = str(submission.status)
                if '.' in status_str:
                    status_value = status_str.split('.')[-1].lower()
                else:
                    status_value = status_str.lower()
            
            return render_template('submission_detail.html',
                                 submission=submission,
                                 participant=participant,
                                 challenge=challenge,
                                 status_value=status_value)
        finally:
            db.close()
    
    @app.route('/participants')
    @login_required
    def participants():
        """View participants"""
        page = int(request.args.get('page', '1'))
        per_page = int(request.args.get('per_page', PARTICIPANTS_PER_PAGE))
        if page < 1:
            page = 1
        if per_page < 1:
            per_page = PARTICIPANTS_PER_PAGE

        cache_key = f"participants:{page}:{per_page}"
        cached = _cache_get(cache_key)
        if cached:
            return render_template('participants.html', **cached)

        db = db_manager.get_session()
        try:
            total = db.query(Participant).count()
            participants_list = db.query(Participant).order_by(Participant.registration_date.desc()).limit(per_page).offset((page - 1) * per_page).all()
            context = {
                'participants': participants_list,
                'page': page,
                'per_page': per_page,
                'total': total
            }
            _cache_set(cache_key, context, PARTICIPANTS_CACHE_TTL_SECONDS)
            return render_template('participants.html', **context)
        finally:
            db.close()
    
    @app.route('/statistics')
    @login_required
    def statistics():
        """View statistics"""
        cached = _cache_get('statistics')
        if cached:
            return render_template('statistics.html', **cached)

        db = db_manager.get_session()
        try:
            # Get various statistics
            total_participants = db.query(Participant).filter(Participant.is_active == True).count()
            total_events = db.query(Event).filter(Event.is_active == True).count()
            total_challenges = db.query(Challenge).filter(Challenge.is_active == True).count()

            # Submissions by status (single grouped query)
            submissions_by_status = {s.value: 0 for s in SubmissionStatus}
            rows = db.query(Submission.status, func.count(Submission.id)).group_by(Submission.status).all()
            for status, count in rows:
                key = status.value if hasattr(status, 'value') else str(status)
                submissions_by_status[key] = count

            context = {
                'total_participants': total_participants,
                'total_events': total_events,
                'total_challenges': total_challenges,
                'submissions_by_status': submissions_by_status
            }
            _cache_set('statistics', context, STATISTICS_CACHE_TTL_SECONDS)
            return render_template('statistics.html', **context)
        finally:
            db.close()
    
    @app.route('/admins')
    @login_required
    def admins():
        """Admin management page"""
        db = db_manager.get_session()
        try:
            admins = db.query(Admin).all()
            return render_template('admins.html', admins=admins)
        finally:
            db.close()

    # УДАЛЕНО: /debug-env endpoint - раскрывал чувствительные данные (DATABASE_URL)
    # Если нужна отладка, используйте логирование или защищённый admin endpoint

    @app.route('/get-file-url')
    @login_required
    def get_file_url():
        """Generate signed URL for R2 files"""
        try:
            from flask import request
            from src.utils.storage import get_storage_manager

            file_path = request.args.get('path')
            if not file_path:
                return {'error': 'Путь к файлу не указан'}, 400

            storage = get_storage_manager()
            logger.debug(f"get_file_url: file_path={file_path}, storage_type={storage.storage_type}")
            url = storage.get_file_url(file_path)
            logger.debug(f"get_file_url: generated url={url}")
            if url:
                return {'url': url}, 200
            else:
                return {'error': 'Файл не найден'}, 404
        except Exception as e:
            logger.error(f"Error generating file URL: {e}")
            return {'error': f'Ошибка получения файла: {str(e)}'}, 500

    @app.route('/debug-media/<int:submission_id>')
    @login_required
    def debug_media(submission_id):
        """Debug media for a specific submission"""
        if os.getenv('ENABLE_DEBUG_ENDPOINTS', 'false').lower() not in ('1', 'true', 'yes'):
            return 'Not Found', 404
        db = db_manager.get_session()
        try:
            submission = db.query(Submission).get(submission_id)
            if not submission:
                return f"<h1>Submission {submission_id} not found</h1>"

            media_path = submission.media_path
            is_r2_url = media_path.startswith('https://') if media_path else False

            html = f"""
            <h1>Media Debug for Submission {submission_id}</h1>
            <p>Media Path: {media_path}</p>
            <p>Is R2 URL: {is_r2_url}</p>
            <p>File Extension: {media_path.split('.')[-1] if media_path and '.' in media_path else 'unknown'}</p>

            <h2>Test Direct Access:</h2>
            """

            if media_path and media_path.startswith('https://'):
                html += f'<p><a href="{media_path}" target="_blank">Direct R2 Link</a></p>'
                html += f'<img src="{media_path}" style="max-width: 300px;" onerror="this.style.display=\'none\'">'
            else:
                html += f'<p>Local file: {media_path}</p>'

            return html
        finally:
            db.close()

    # setup-demo route removed

    @app.route('/run-migration-registrations')
    @login_required
    def run_migration_registrations():
        """Temporary endpoint to run registrations migration"""
        try:
            import subprocess
            import os

            # Get project root
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            script_path = os.path.join(project_root, 'migrate_registrations.py')

            # Run migration script
            result = subprocess.run(
                ['python3', script_path],
                capture_output=True,
                text=True,
                timeout=60
            )

            output = f"<h1>Migration Output</h1><pre>{result.stdout}</pre>"
            if result.stderr:
                output += f"<h2>Errors:</h2><pre>{result.stderr}</pre>"
            output += f"<p>Exit code: {result.returncode}</p>"

            return output
        except Exception as e:
            return f"<h1>Error running migration</h1><pre>{str(e)}</pre>"

    @app.route('/admins/add', methods=['POST'])
    @login_required
    def add_admin():
        """Add new administrator"""
        try:
            telegram_id = request.form['telegram_id'].strip()
            username = request.form.get('username', '').strip() or None
            full_name = request.form.get('full_name', '').strip() or None
            
            if not telegram_id.isdigit():
                flash('Telegram ID должен быть числом', 'error')
                return redirect(url_for('admins'))
            
            db = db_manager.get_session()
            try:
                # Check if admin already exists
                existing_admin = db.query(Admin).filter(Admin.telegram_id == telegram_id).first()
                if existing_admin:
                    if existing_admin.is_active:
                        flash('Администратор с таким Telegram ID уже существует', 'error')
                    else:
                        # Reactivate existing admin
                        existing_admin.is_active = True
                        existing_admin.username = username
                        existing_admin.full_name = full_name
                        existing_admin.added_at = datetime.utcnow()
                        db.commit()
                        flash('Администратор успешно восстановлен!', 'success')
                else:
                    # Create new admin
                    new_admin = Admin(
                        telegram_id=telegram_id,
                        username=username,
                        full_name=full_name,
                        added_by=session.get('admin_username', 'web_admin')
                    )
                    db.add(new_admin)
                    db.commit()
                    flash('Администратор успешно добавлен!', 'success')
            finally:
                db.close()
        except Exception as e:
            flash(f'Ошибка при добавлении администратора: {str(e)}', 'error')
        
        return redirect(url_for('admins'))
    
    @app.route('/admins/<int:admin_id>/delete', methods=['POST'])
    @login_required
    def delete_admin(admin_id):
        """Delete administrator permanently"""
        try:
            db = db_manager.get_session()
            try:
                admin = db.query(Admin).filter(Admin.id == admin_id).first()
                if not admin:
                    flash('Администратор не найден', 'error')
                    return redirect(url_for('admins'))
                
                # Prevent deletion of the last admin
                active_admins_count = db.query(Admin).filter(Admin.is_active == True).count()
                if active_admins_count <= 1:
                    flash('Нельзя удалить последнего активного администратора', 'error')
                    return redirect(url_for('admins'))
                
                # Permanent deletion
                db.delete(admin)
                db.commit()
                flash('Администратор успешно удален!', 'success')
            finally:
                db.close()
        except Exception as e:
            flash(f'Ошибка при удалении администратора: {str(e)}', 'error')
        
        return redirect(url_for('admins'))
    
    @app.route('/admins/<int:admin_id>/deactivate', methods=['POST'])
    @login_required
    def deactivate_admin(admin_id):
        """Deactivate administrator (soft delete)"""
        try:
            db = db_manager.get_session()
            try:
                admin = db.query(Admin).filter(Admin.id == admin_id).first()
                if not admin:
                    flash('Администратор не найден', 'error')
                    return redirect(url_for('admins'))
                
                # Prevent deactivation of the last admin
                active_admins_count = db.query(Admin).filter(Admin.is_active == True).count()
                if active_admins_count <= 1 and admin.is_active:
                    flash('Нельзя деактивировать последнего активного администратора', 'error')
                    return redirect(url_for('admins'))
                
                # Soft delete
                admin.is_active = False
                db.commit()
                flash('Администратор успешно деактивирован!', 'success')
            finally:
                db.close()
        except Exception as e:
            flash(f'Ошибка при деактивации администратора: {str(e)}', 'error')
        
        return redirect(url_for('admins'))

    def _get_or_create_ai_settings(db):
        settings = db.query(AIWorkerSettings).first()
        if settings:
            return settings
        settings = AIWorkerSettings()
        db.add(settings)
        db.commit()
        db.refresh(settings)
        return settings

    def _ensure_ai_test_columns(db_manager):
        """Ensure ai_test_results has status/updated_at columns (for legacy DBs)."""
        try:
            engine = db_manager.engine
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE ai_test_results ADD COLUMN IF NOT EXISTS status text DEFAULT 'queued'"))
                conn.execute(text("ALTER TABLE ai_test_results ADD COLUMN IF NOT EXISTS updated_at timestamptz DEFAULT NOW()"))
                conn.commit()
        except Exception as e:
            logger.warning(f"ai_test_results migration skipped/failed: {e}")

    @app.route('/ai-settings', methods=['POST'])
    @login_required
    def ai_settings_update():
        db = db_manager.get_session()
        try:
            settings = _get_or_create_ai_settings(db)

            field_map = {
                "min_confidence": float,
                "min_pose_detection_rate": float,
                "min_video_duration": int,
                "frame_skip": int,
                "pose_visibility_min": float,
                "angle_smoothing_alpha": float,
                "phase_debounce_frames": int,
                "pushup_down_threshold": float,
                "pushup_up_threshold": float,
                "squat_down_threshold": float,
                "squat_up_threshold": float,
                "mediapipe_min_detection_confidence": float,
                "mediapipe_min_tracking_confidence": float,
                "max_processing_time": int,
            }

            for field, cast in field_map.items():
                raw_value = request.form.get(field)
                if raw_value is None or raw_value == "":
                    continue
                try:
                    setattr(settings, field, cast(raw_value))
                except ValueError:
                    flash(f"Некорректное значение для {field}", "error")
                    return redirect(url_for('ai_reports'))

            db.commit()
            flash("Настройки AI Worker сохранены", "success")
        except Exception as e:
            db.rollback()
            flash(f"Ошибка сохранения настроек: {str(e)}", "error")
        finally:
            db.close()

        return redirect(url_for('ai_reports'))

    @app.route('/ai-test', methods=['POST'])
    @login_required
    def ai_test():
        _ensure_ai_test_columns(db_manager)
        worker_url = os.getenv("AI_WORKER_URL", "").strip()
        api_key = os.getenv("AI_WORKER_API_KEY", "").strip()

        if not worker_url:
            flash("AI_WORKER_URL не задан", "error")
            return redirect(url_for('ai_reports'))

        video_file = request.files.get("video")
        exercise_type = request.form.get("exercise_type", "push_ups")

        if not video_file or video_file.filename == "":
            flash("Выберите видео для теста", "error")
            return redirect(url_for('ai_reports'))

        db = db_manager.get_session()
        try:
            files = {
                "video": (video_file.filename, video_file.stream, video_file.content_type or "video/mp4")
            }
            data = {"exercise_type": exercise_type}
            headers = {}
            if api_key:
                headers["X-API-Key"] = api_key

            response = requests.post(
                worker_url.rstrip("/") + "/analyze-test",
                files=files,
                data=data,
                headers=headers,
                timeout=300
            )

            if response.ok:
                result = response.json()
                test_row = AITestResult(
                    exercise_type=exercise_type,
                    result_json=json.dumps(result, ensure_ascii=False),
                    error_message=None
                )
                db.add(test_row)
                db.commit()
            else:
                test_row = AITestResult(
                    exercise_type=exercise_type,
                    result_json=None,
                    error_message=f"{response.status_code}: {response.text}"
                )
                db.add(test_row)
                db.commit()
                response_error = test_row.error_message
        except Exception as e:
            test_row = AITestResult(
                exercise_type=exercise_type,
                result_json=None,
                error_message=str(e)
            )
            db.add(test_row)
            db.commit()
            response_error = test_row.error_message
        finally:
            db.close()

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({
                "result": result if 'result' in locals() else None,
                "error": response_error
            })

        return redirect(url_for('ai_reports'))

    @app.route('/ai-test/clear', methods=['POST'])
    @login_required
    def ai_test_clear():
        _ensure_ai_test_columns(db_manager)
        db = db_manager.get_session()
        try:
            db.query(AITestResult).delete()
            db.commit()
        finally:
            db.close()
        return redirect(url_for('ai_reports'))

    @app.route('/ai-reports')
    @login_required
    def ai_reports():
        """View AI analysis reports dashboard"""
        _ensure_ai_test_columns(db_manager)
        db = db_manager.get_session()
        try:
            # Get all AI analyses with related data
            analyses = db.query(AIAnalysis, Submission, Participant, Challenge).join(
                Submission, AIAnalysis.submission_id == Submission.id
            ).join(
                Participant, Submission.participant_id == Participant.id
            ).join(
                Challenge, Submission.challenge_id == Challenge.id
            ).order_by(AIAnalysis.created_at.desc()).limit(100).all()

            # Count by status
            stats = {
                'total': db.query(AIAnalysis).count(),
                'queued': db.query(AIAnalysis).filter(AIAnalysis.status == AIAnalysisStatus.QUEUED).count(),
                'processing': db.query(AIAnalysis).filter(AIAnalysis.status == AIAnalysisStatus.PROCESSING).count(),
                'completed': db.query(AIAnalysis).filter(AIAnalysis.status == AIAnalysisStatus.COMPLETED).count(),
                'failed': db.query(AIAnalysis).filter(AIAnalysis.status == AIAnalysisStatus.FAILED).count(),
                'manual_required': db.query(AIAnalysis).filter(AIAnalysis.status == AIAnalysisStatus.MANUAL_REQUIRED).count(),
            }

            # Format data for template
            reports = []
            for ai_analysis, submission, participant, challenge in analyses:
                reports.append({
                    'ai_analysis': submission.ai_analysis,
                    'submission': submission,
                    'participant': participant,
                    'challenge': challenge
                })

            settings = _get_or_create_ai_settings(db)
            test_row = db.query(AITestResult).order_by(AITestResult.created_at.desc()).first()
            test_result = None
            test_error = None
            test_status = None
            if test_row:
                test_error = test_row.error_message
                test_status = test_row.status
                if test_row.result_json:
                    try:
                        test_result = json.loads(test_row.result_json)
                    except Exception:
                        test_result = None

            return render_template('ai_reports.html',
                                 reports=reports,
                                 stats=stats,
                                 settings=settings,
                                 test_result=test_result,
                                 test_error=test_error,
                                 test_status=test_status,
                                 AIAnalysisStatus=AIAnalysisStatus)
        finally:
            db.close()

    return app

if __name__ == '__main__':
    app = create_app()
    port = int(os.getenv('PORT', os.getenv('WEB_PORT', '5000')))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)
