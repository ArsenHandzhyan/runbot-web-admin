"""
Web Admin Interface for RunBot
Simple Flask-based admin panel for managing events, challenges and participants
"""

import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from functools import wraps
import logging
from datetime import datetime

from src.database.db import DatabaseManager
from src.models.models import Participant, Event, Challenge, ChallengeType, Submission, SubmissionStatus
from src.utils.event_manager import EventManager
from src.utils.challenge_manager import ChallengeManager
import telebot

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
    bot = telebot.TeleBot(os.getenv('TELEGRAM_BOT_TOKEN'))
    event_manager = EventManager(bot, db_manager)
    challenge_manager = ChallengeManager(bot, db_manager)
    
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
            
            # Get recent activity
            recent_events = db.query(Event).filter(Event.is_active == True).order_by(Event.created_at.desc()).limit(5).all()
            recent_challenges = db.query(Challenge).filter(Challenge.is_active == True).order_by(Challenge.created_at.desc()).limit(5).all()
            
            return render_template('dashboard.html',
                                 participants_count=participants_count,
                                 events_count=events_count,
                                 challenges_count=challenges_count,
                                 submissions_count=submissions_count,
                                 recent_events=recent_events,
                                 recent_challenges=recent_challenges)
        finally:
            db.close()
    
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
    
    @app.route('/challenges')
    @login_required
    def challenges():
        """Manage challenges"""
        db = db_manager.get_session()
        try:
            challenges_list = db.query(Challenge).order_by(Challenge.created_at.desc()).all()
            return render_template('challenges.html', challenges=challenges_list, ChallengeType=ChallengeType)
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
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='0.0.0.0', port=int(os.getenv('WEB_PORT', 5000)), debug=True)