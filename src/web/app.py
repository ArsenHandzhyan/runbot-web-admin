"""
Web Admin Interface for RunBot
Simple Flask-based admin panel for managing events, challenges and participants
"""

import os
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from functools import wraps
import logging

# Removed problematic import: from src.web.test_media import test_media_blueprint
# This import was causing deployment failures on Render.com
from datetime import datetime

from src.database.db import DatabaseManager
from src.models.models import Participant, Event, Challenge, ChallengeType, Submission, SubmissionStatus, Admin, EventType, ChallengeRegistration
from src.utils.event_manager import EventManager
from src.utils.challenge_manager import ChallengeManager
# NOTE: telebot import removed - web interface doesn't need bot functionality

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app():
    # Get the project root directory
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    app = Flask(__name__, 
                template_folder=os.path.join(project_root, 'templates'),
                static_folder=os.path.join(project_root, 'static'))
    app.secret_key = os.getenv('WEB_SECRET_KEY', 'your-secret-key-change-in-production')
    
    # Initialize managers
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
        try:
            # Get counts for dashboard
            participants_count = db.query(Participant).filter(Participant.is_active == True).count()
            events_count = db.query(Event).filter(Event.is_active == True).count()
            challenges_count = db.query(Challenge).filter(Challenge.is_active == True).count()
            submissions_count = db.query(Submission).count()
            pending_submissions_count = db.query(Submission).filter(
                Submission.status == SubmissionStatus.PENDING
            ).count()
            
            # Get recent activity
            recent_events = db.query(Event).filter(Event.is_active == True).order_by(Event.created_at.desc()).limit(5).all()
            recent_challenges = db.query(Challenge).filter(Challenge.is_active == True).order_by(Challenge.created_at.desc()).limit(5).all()
            
            return render_template('dashboard.html',
                                 participants_count=participants_count,
                                 events_count=events_count,
                                 challenges_count=challenges_count,
                                 submissions_count=submissions_count,
                                 pending_submissions_count=pending_submissions_count,
                                 recent_events=recent_events,
                                 recent_challenges=recent_challenges)
        finally:
            db.close()
    
    @app.route('/media/<path:filename>')
    def serve_media(filename):
        """Serve media files from media directory"""
        # Compute project root reliably and serve media from there
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        media_path = os.path.join(repo_root, 'media')
        logger.info("serve_media: filename=%s, media_path=%s, exists=%s", filename, media_path, os.path.exists(os.path.join(media_path, filename)))
        try:
            return send_from_directory(media_path, filename)
        except Exception as e:
            logger.exception("serve_media error: %s", e)
            raise

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """Admin login"""
        if request.method == 'POST':
            username = request.form['username']
            password = request.form['password']
            
            # Simple auth check (in production use proper auth system)
            admin_username = os.getenv('ADMIN_USERNAME', 'admin')
            admin_password = os.getenv('ADMIN_PASSWORD', 'admin123')
            
            if username == admin_username and password == admin_password:
                session['admin_logged_in'] = True
                session['admin_username'] = username
                flash('Успешный вход в систему!', 'success')
                return redirect(url_for('index'))
            else:
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
        """Delete event"""
        db = db_manager.get_session()
        try:
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                flash('Событие не найдено', 'error')
                return redirect(url_for('events'))
            
            # Check if event has registrations
            if event.registrations:
                flash('Нельзя удалить событие с участниками', 'error')
                return redirect(url_for('events'))
            
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
        db = db_manager.get_session()
        try:
            # Get all challenges
            challenges_list = db.query(Challenge).order_by(Challenge.created_at.desc()).all()
            
            # Add participant and submission counts to each challenge
            challenges_with_counts = []
            for challenge in challenges_list:
                # Count participants
                participant_count = db.query(ChallengeRegistration).filter(
                    ChallengeRegistration.challenge_id == challenge.id,
                    ChallengeRegistration.is_active == True
                ).count()
                
                # Count submissions
                submission_count = db.query(Submission).filter(
                    Submission.challenge_id == challenge.id
                ).count()
                
                # Add counts to challenge object
                challenge.participant_count = participant_count
                challenge.submission_count = submission_count
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
            submissions = db.query(Submission).filter(
                Submission.challenge_id == challenge_id
            ).order_by(Submission.submission_date.desc()).all()
            
            # Get participant info for each submission and prepare data for template
            submissions_with_participants = []
            for submission in submissions:
                participant = db.query(Participant).filter(
                    Participant.id == submission.participant_id
                ).first()
                
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
                    'status_value': status_value
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
                pending_submissions = db.query(Submission).filter(
                    Submission.status == SubmissionStatus.PENDING
                ).order_by(Submission.submission_date.asc()).all()

                # Get all submissions (for overview)
                all_submissions = db.query(Submission).order_by(Submission.submission_date.desc()).limit(50).all()
            except Exception as e:
                # Log and render with empty data to avoid 500 on UI
                logger.exception("Ошибка при загрузке данных модерации: %s", e)
                pending_submissions = []
                all_submissions = []

            # Prepare data for templates
            pending_with_details = []
            all_with_details = []

            for submission in pending_submissions:
                participant = db.query(Participant).filter(
                    Participant.id == submission.participant_id
                ).first()
                challenge = db.query(Challenge).filter(
                    Challenge.id == submission.challenge_id
                ).first()

                pending_with_details.append({
                    'submission': submission,
                    'participant': participant,
                    'challenge': challenge
                })

            for submission in all_submissions:
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

                all_with_details.append({
                    'submission': submission,
                    'participant': participant,
                    'challenge': challenge,
                    'status_value': status_value
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
        db = db_manager.get_session()
        try:
            participants_list = db.query(Participant).order_by(Participant.registration_date.desc()).all()
            return render_template('participants.html', participants=participants_list)
        finally:
            db.close()
    
    @app.route('/statistics')
    @login_required
    def statistics():
        """View statistics"""
        db = db_manager.get_session()
        try:
            # Get various statistics
            total_participants = db.query(Participant).filter(Participant.is_active == True).count()
            total_events = db.query(Event).filter(Event.is_active == True).count()
            total_challenges = db.query(Challenge).filter(Challenge.is_active == True).count()
            
            # Submissions by status
            submissions_by_status = {}
            for status in SubmissionStatus:
                count = db.query(Submission).filter(Submission.status == status).count()
                submissions_by_status[status.value] = count
            
            return render_template('statistics.html',
                                 total_participants=total_participants,
                                 total_events=total_events,
                                 total_challenges=total_challenges,
                                 submissions_by_status=submissions_by_status)
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

    @app.route('/setup-demo')
    @login_required
    def setup_demo():
        """Setup demo data for testing"""
        from src.models.models import Participant, Challenge, Submission, ChallengeType, SubmissionStatus
        from datetime import datetime, timedelta

        db = db_manager.get_session()
        try:
            # Check if demo data already exists
            existing_submissions = db.query(Submission).count()
            if existing_submissions > 0:
                flash(f'Демо-данные уже существуют ({existing_submissions} отчетов)', 'info')
                return redirect(url_for('moderation'))

            # Create demo participants
            participants_data = [
                {'telegram_id': '111111111', 'full_name': 'Алексей Петров', 'birth_date': datetime(1995, 3, 15).date(), 'phone': '+7-999-111-11-11', 'start_number': 'P001'},
                {'telegram_id': '222222222', 'full_name': 'Мария Иванова', 'birth_date': datetime(1992, 7, 22).date(), 'phone': '+7-999-222-22-22', 'start_number': 'P002'},
                {'telegram_id': '333333333', 'full_name': 'Дмитрий Сидоров', 'birth_date': datetime(1988, 12, 5).date(), 'phone': '+7-999-333-33-33', 'start_number': 'P003'}
            ]

            participants = []
            for p_data in participants_data:
                participant = Participant(**p_data)
                db.add(participant)
                participants.append(participant)

            # Create demo challenges
            challenges_data = [
                {'name': 'Отжимания 50 раз', 'description': 'Выполните 50 отжиманий за тренировку', 'challenge_type': ChallengeType.PUSH_UPS, 'start_date': datetime.now() - timedelta(days=5), 'end_date': datetime.now() + timedelta(days=10), 'is_active': True},
                {'name': 'Бег 10 км', 'description': 'Пробегите 10 километров за неделю', 'challenge_type': ChallengeType.RUNNING, 'start_date': datetime.now() - timedelta(days=3), 'end_date': datetime.now() + timedelta(days=12), 'is_active': True},
                {'name': 'Планка 3 минуты', 'description': 'Удерживайте планку 3 минуты', 'challenge_type': ChallengeType.PLANK, 'start_date': datetime.now() - timedelta(days=7), 'end_date': datetime.now() + timedelta(days=8), 'is_active': True}
            ]

            challenges = []
            for c_data in challenges_data:
                challenge = Challenge(**c_data)
                db.add(challenge)
                challenges.append(challenge)

            # Demo files (placeholder names for Cloudflare R2)
            demo_files = ['demo-text-001.txt', 'demo-excel-001.csv', 'demo-document-001.pdf', 'demo-image-001.jpg', 'demo-video-001.mp4', 'demo-video-002.mp4']

            # Create demo submissions
            submissions_data = [
                {'participant': participants[0], 'challenge': challenges[0], 'result_value': 50.0, 'result_unit': 'отжиманий', 'comment': 'Отлично выполнил! Прилагаю фото тренировки.', 'media_path': demo_files[0], 'status': SubmissionStatus.APPROVED},
                {'participant': participants[1], 'challenge': challenges[1], 'result_value': 10.5, 'result_unit': 'км', 'comment': 'Пробежал 10.5 км! GPS трек во вложении.', 'media_path': demo_files[1], 'status': SubmissionStatus.APPROVED},
                {'participant': participants[2], 'challenge': challenges[2], 'result_value': 3.2, 'result_unit': 'минуты', 'comment': 'Удержал планку 3 минуты 12 секунд! Видео прилагаю.', 'media_path': demo_files[2], 'status': SubmissionStatus.PENDING},
                {'participant': participants[0], 'challenge': challenges[1], 'result_value': 8.7, 'result_unit': 'км', 'comment': 'Сегодняшняя пробежка. Фото с маршрута.', 'media_path': demo_files[3], 'status': SubmissionStatus.PENDING},
                {'participant': participants[1], 'challenge': challenges[0], 'result_value': 45.0, 'result_unit': 'отжиманий', 'comment': '45 отжиманий! Результаты тренировки в PDF.', 'media_path': demo_files[4], 'status': SubmissionStatus.PENDING},
                {'participant': participants[2], 'challenge': challenges[1], 'result_value': 12.3, 'result_unit': 'км', 'comment': 'Длинная пробежка! Видео с маршрута.', 'media_path': demo_files[5], 'status': SubmissionStatus.APPROVED}
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

            flash(f'Создано {len(participants)} участников, {len(challenges)} челленджей и {len(submissions)} отчетов с файлами!', 'success')
            return redirect(url_for('moderation'))

        except Exception as e:
            db.rollback()
            flash(f'Ошибка при создании демо-данных: {str(e)}', 'error')
            return redirect(url_for('moderation'))
        finally:
            db.close()
    
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
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('WEB_PORT', 5000)), debug=True)
