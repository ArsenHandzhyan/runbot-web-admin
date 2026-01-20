"""
Main Telegram Bot Implementation
Handles all bot commands and user interactions
"""

import sys
import os

# Add parent directory to Python path for imports to work
# This is needed when running from src/bot/main.py directly
parent_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

import telebot
import logging
from datetime import datetime
from typing import Optional

from src.database.db import get_db_manager
from src.models.models import Participant, Challenge, Submission, DistanceType, Event, EventStatus
from src.utils.registration import RegistrationManager
from src.utils.challenge_manager import ChallengeManager
from src.utils.event_manager import EventManager
from src.admin.admin_panel import AdminPanel

logger = logging.getLogger(__name__)

class RunBot:
    """Main RunBot class"""
    
    def __init__(self):
        self.token = os.getenv('TELEGRAM_BOT_TOKEN')
        if not self.token:
            raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

        # Support both ADMIN_TELEGRAM_ID (single) and ADMIN_TELEGRAM_IDS (multiple)
        admin_ids_str = os.getenv('ADMIN_TELEGRAM_IDS') or os.getenv('ADMIN_TELEGRAM_ID')
        if not admin_ids_str:
            raise ValueError("ADMIN_TELEGRAM_IDS or ADMIN_TELEGRAM_ID environment variable is required")

        logger.info(f"Loading admin IDs from env: {admin_ids_str}")

        # Parse admin IDs (can be comma-separated)
        admin_ids = [id.strip() for id in admin_ids_str.split(',') if id.strip()]
        if not admin_ids:
            raise ValueError("At least one admin ID is required")

        # Use first admin as primary
        self.admin_id = admin_ids[0]
        self.admin_ids = admin_ids

        logger.info(f"Configured admin IDs: {self.admin_ids}")

        self.bot = telebot.TeleBot(self.token)
        self.db_manager = get_db_manager()
        self.registration_manager = RegistrationManager(self.bot, self.db_manager)
        self.challenge_manager = ChallengeManager(self.bot, self.db_manager)
        self.event_manager = EventManager(self.bot, self.db_manager)

        # Track which users are in admin panel context
        self.users_in_admin_panel = set()

        # Create admin panel with callback to remove user from tracking
        self.admin_panel = AdminPanel(self.bot, self.db_manager, self.admin_id,
                                     remove_user_from_admin_panel_func=self._remove_user_from_admin_panel)

        self._setup_handlers()

    def _add_user_to_admin_panel(self, user_id: str):
        """Add user to admin panel context"""
        self.users_in_admin_panel.add(user_id)
        logger.info(f"User {user_id} entered admin panel context")

    def _remove_user_from_admin_panel(self, user_id: str):
        """Remove user from admin panel context"""
        if user_id in self.users_in_admin_panel:
            self.users_in_admin_panel.remove(user_id)
            logger.info(f"User {user_id} left admin panel context")

    def is_admin(self, user_id: int) -> bool:
        """Check if user is an admin"""
        return str(user_id) in self.admin_ids

    def _setup_handlers(self):
        """Setup all bot command handlers"""
        @self.bot.message_handler(commands=['start'])
        def send_welcome(message):
            self._handle_start(message)
        
        @self.bot.message_handler(commands=['register'])
        def register_participant(message):
            self._handle_registration(message)
        
        @self.bot.message_handler(commands=['events'])
        def show_events(message):
            self._handle_show_events(message)

        @self.bot.message_handler(commands=['challenges'])
        def show_challenges(message):
            self._handle_show_challenges(message)

        @self.bot.message_handler(commands=['submit'])
        def submit_report(message):
            self._handle_submit_report(message)
        
        @self.bot.message_handler(commands=['stats'])
        def show_stats(message):
            self._handle_show_stats(message)
        
        @self.bot.message_handler(commands=['help'])
        def send_help(message):
            self._handle_help(message)
        
        # Admin commands
        @self.bot.message_handler(commands=['admin'])
        def admin_panel(message):
            if self.is_admin(message.from_user.id):
                self.admin_panel.show_main_menu(message)
            else:
                self.bot.reply_to(message, "Access denied. Admin only.")
        
        # Handle document/photo uploads
        @self.bot.message_handler(content_types=['photo', 'video', 'document'])
        def handle_media_upload(message):
            self._handle_media_upload(message)
        
        # Handle callback queries (for inline buttons)
        @self.bot.callback_query_handler(func=lambda call: True)
        def handle_callback(call):
            self._handle_callback_query(call)
        
        # Handle text messages (for registration flow)
        @self.bot.message_handler(func=lambda message: True)
        def handle_text(message):
            self._handle_text_message(message)
    
    def _handle_start(self, message):
        """Handle /start command"""
        welcome_text = """
🏃‍♂️ *Добро пожаловать в RunBot!*

Я помогу вам участвовать в спортивных челленджах и забегах!

*Доступные команды:*
/register - регистрация на забег
/events - список событий
/challenges - список доступных челленджей
/submit - отправить отчет о выполнении
/stats - ваша статистика
/help - помощь

Выберите действие:
        """

        # Check if user is registered
        session = self.db_manager.get_session()
        try:
            participant = session.query(Participant).filter_by(telegram_id=str(message.from_user.id)).first()
            is_registered = participant is not None
        finally:
            session.close()

        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)

        if is_registered:
            # Show menu without registration button
            markup.row('🎉 События', '🏆 Челленджи')
            markup.row('📊 Статистика', 'ℹ️ Помощь')
        else:
            # Show menu with registration button
            markup.row('🏃 Регистрация')
            markup.row('🎉 События', '🏆 Челленджи')
            markup.row('📊 Статистика', 'ℹ️ Помощь')

        # Add admin button for admins
        user_id = message.from_user.id
        is_admin_user = self.is_admin(user_id)
        logger.info(f"User {user_id} requesting /start, is_admin={is_admin_user}, admin_ids={self.admin_ids}")

        if is_admin_user:
            markup.row('🔐 Админ-панель')
            logger.info(f"Added admin panel button for user {user_id}")

        self.bot.reply_to(message, welcome_text, parse_mode='Markdown', reply_markup=markup)
    
    def _handle_registration(self, message):
        """Handle registration command"""
        self.registration_manager.start_registration(message.chat.id)

    def _handle_show_events(self, message):
        """Show available events for regular users"""
        logger.info(f"_handle_show_events called for user {message.from_user.id}")
        self.event_manager.show_available_events(message.chat.id)

    def _handle_show_challenges(self, message):
        """Show available challenges"""
        self.challenge_manager.show_active_challenges(message.chat.id)
    
    def _handle_submit_report(self, message):
        """Handle report submission"""
        self.challenge_manager.start_submission_process(message.chat.id)
    
    def _handle_show_stats(self, message):
        """Show user statistics"""
        self.challenge_manager.show_user_stats(message.chat.id)
    
    def _handle_distance_selection_for_event(self, message):
        """Handle distance selection during event registration"""
        chat_id = message.chat.id
        chat_id_str = str(chat_id)
        text = message.text

        # Determine distance type
        distance_type = DistanceType.ADULT_RUN if 'Взрослый' in text else DistanceType.CHILDREN_RUN

        # Update participant's distance type
        db = self.db_manager.get_session()
        try:
            participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id),
                Participant.is_active == True
            ).first()

            if participant:
                participant.distance_type = distance_type
                db.commit()

                # Get event data from temporary storage
                event_data = self.event_manager.temp_distance_selection[chat_id_str]
                event_id = event_data['event_id']

                # Remove from temporary storage
                del self.event_manager.temp_distance_selection[chat_id_str]

                # Complete event registration with distance
                logger.info(f"Distance {distance_type.value} selected for participant {participant.id}, registering for event {event_id}")
                registration_success = self.event_manager.register_for_event(chat_id, event_id)

                # Show confirmation with distance name
                distance_name = 'Взрослый забег' if distance_type == DistanceType.ADULT_RUN else 'Детский забег'
                self.bot.reply_to(message, f"✅ Дистанция сохранена: {distance_name}")

                # Auto-refresh events list after successful registration
                if registration_success:
                    logger.info(f"Refreshing events list after distance selection for user {chat_id}")
                    self.event_manager.show_available_events(chat_id)
            else:
                self.bot.reply_to(message, "Ошибка: участник не найден")
                if chat_id_str in self.event_manager.temp_distance_selection:
                    del self.event_manager.temp_distance_selection[chat_id_str]

        except Exception as e:
            db.rollback()
            logger.error(f"Error updating distance type: {e}")
            self.bot.reply_to(message, "Ошибка при обновлении дистанции")
            if chat_id_str in self.event_manager.temp_distance_selection:
                del self.event_manager.temp_distance_selection[chat_id_str]
        finally:
            db.close()

    def _handle_help(self, message):
        """Handle help command - shows different help for admins and users"""
        user_id = message.from_user.id
        is_admin = self.is_admin(user_id)

        if is_admin:
            # Help for administrators
            help_text = """
❓ *Помощь по RunBot - Администратор*

👤 *Ваш статус:* Администратор

*📱 ГЛАВНОЕ МЕНЮ (для участия):*
• 🎉 События - просмотр и регистрация на события
• 🏆 Челленджи - участие в челленджах
• 📊 Статистика - ваша статистика участника
• ℹ️ Помощь - это сообщение

*🔐 АДМИН-ПАНЕЛЬ:*
• 🔐 Админ-панель - войти в режим управления

*Разделы админ-панели:*
• 👥 Участники - управление участниками
• 🏆 Челленджи - создание и управление челленджами
• 🎉 События - создание и управление событиями
• 📊 Статистика - общая статистика системы
• 🔍 Модерация - проверка отчётов участников
• 📤 Экспорт - экспорт данных в Excel
• ⚙️ Настройки - настройки системы

*💡 Совет:*
Используйте кнопку 🏠 Главное меню для переключения между режимом участника и админ-панелью.

*Команды:*
• /admin - быстрый вход в админ-панель
• /start - вернуться в главное меню
• /help - показать эту справку
            """
        else:
            # Help for regular users
            help_text = """
❓ *Помощь по RunBot*

👤 *Ваш статус:* Участник

*📱 ГЛАВНОЕ МЕНЮ:*
• 🏃 Регистрация - зарегистрироваться как участник
• 🎉 События - просмотр и регистрация на события
• 🏆 Челленджи - участие в челленджах
• 📊 Статистика - ваша статистика
• ℹ️ Помощь - это сообщение

*🎯 Как начать:*
1. Нажмите 🏃 Регистрация
2. Укажите ФИО, дату рождения и телефон
3. Выберите дистанцию (взрослый/детский забег)
4. Получите стартовый номер
5. Участвуйте в событиях и челленджах!

*🏆 Доступные челленджи:*
• 💪 Отжимания
• 🦵 Приседания
• 🧘 Планка
• 🏃 Бег
• 👣 Шагомер

*🎉 Типы событий:*
• 🏃 Забеги - спортивные забеги
• 🏅 Турниры - соревнования
• 🏆 Челленджи - групповые челленджи

*Команды:*
• /register - быстрая регистрация
• /events - посмотреть события
• /challenges - посмотреть челленджи
• /stats - ваша статистика
• /help - показать эту справку
            """

        self.bot.reply_to(message, help_text, parse_mode='Markdown')
    
    def _handle_media_upload(self, message):
        """Handle media uploads"""
        # Check if user is in registration process
        if hasattr(self.registration_manager, 'active_registrations'):
            if message.chat.id in self.registration_manager.active_registrations:
                self.registration_manager.handle_media_upload(message)
                return
        
        # Check if user is submitting report
        if hasattr(self.challenge_manager, 'active_submissions'):
            if message.chat.id in self.challenge_manager.active_submissions:
                self.challenge_manager.handle_media_upload(message)
                return
        
        # If not in any process, ask what they want to do
        self.bot.reply_to(message, "Что вы хотите сделать? Используйте команды /submit для отправки отчета или /register для регистрации.")
    
    def _handle_callback_query(self, call):
        """Handle callback queries from inline buttons"""
        try:
            callback_data = call.data

            # Route callback based on type, not user role
            # Event-related callbacks (check FIRST - for all users including admins)
            if callback_data.startswith(('event_', 'events_')):
                logger.info(f"Routing event callback '{callback_data}' to event manager")
                self.event_manager.handle_callback_query(call)
            # Challenge-related callbacks (for all users including admins)
            elif callback_data.startswith(('challenge_', 'challenges_')):
                logger.info(f"Routing challenge callback '{callback_data}' to challenge manager")
                self.challenge_manager.handle_callback_query(call)
            # Registration callbacks
            elif callback_data.startswith('register_'):
                self.registration_manager.handle_callback_query(call)
            # Admin panel callbacks (only for admins, checked AFTER user callbacks to avoid conflicts)
            elif callback_data.startswith('admin_') or callback_data.startswith(('create_', 'list_')) or callback_data in [
                'participants', 'moderation', 'export', 'statistics', 'settings',
                'participants_events', 'participants_challenges', 'participants_menu',
                'participants_adult', 'participants_children', 'participants_all',
                'admin_participants', 'admin_challenges', 'admin_events',
                'general_stats', 'leaderboard', 'period_stats'
            ]:
                if self.is_admin(call.from_user.id):
                    logger.info(f"Routing admin callback '{callback_data}' to admin panel")
                    self.admin_panel.handle_callback_query(call)
                else:
                    logger.warning(f"🚨 Unauthorized admin access attempt by user {call.from_user.id}, callback: {callback_data}")
                    self.bot.answer_callback_query(call.id, "Функция доступна только администраторам")
            else:
                # Unknown callback
                self.bot.answer_callback_query(call.id, "Неизвестная команда")
        except Exception as e:
            logger.error(f"Callback handling error: {e}")
            import traceback
            traceback.print_exc()
            self.bot.answer_callback_query(call.id, "Ошибка обработки запроса")
    
    def _handle_text_message(self, message):
        """Handle text messages during registration or submission process"""
        # Handle registration flow
        if hasattr(self.registration_manager, 'active_registrations'):
            if message.chat.id in self.registration_manager.active_registrations:
                self.registration_manager.handle_text_input(message)
                return
        
        # Handle submission flow
        if hasattr(self.challenge_manager, 'active_submissions'):
            if message.chat.id in self.challenge_manager.active_submissions:
                self.challenge_manager.handle_text_input(message)
                return
        
        # Handle admin challenge/event creation flow
        if hasattr(self.admin_panel, 'active_admin_sessions'):
            if message.chat.id in self.admin_panel.active_admin_sessions:
                session = self.admin_panel.active_admin_sessions[message.chat.id]

                # Verify admin context to prevent conflicts
                if session.get('context') == 'admin':
                    step = session.get('step', '')

                    # Route to appropriate handler based on session type
                    if 'event' in step:
                        # Event creation session
                        logger.info(f"Routing text to event creation handler for admin {message.from_user.id}")
                        self.admin_panel.handle_event_creation_text(message)
                        return
                    elif 'challenge' in step or step in ['start_date', 'end_date', 'confirm']:
                        # Challenge creation session
                        logger.info(f"Routing text to challenge creation handler for admin {message.from_user.id}")
                        self.admin_panel.handle_challenge_creation_text(message)
                        return
        
        # Handle distance selection for event registration
        chat_id_str = str(message.chat.id)
        if hasattr(self.event_manager, 'temp_distance_selection'):
            if chat_id_str in self.event_manager.temp_distance_selection:
                if message.text in ['🏃 Взрослый забег', '👶 Детский забег']:
                    self._handle_distance_selection_for_event(message)
                    return

        # Handle button clicks
        text = message.text
        # Handle main menu button first (works for both users and admins)
        if text == '🏠 Главное меню':
            # Remove user from admin panel context if they were there
            user_id_str = str(message.from_user.id)
            if user_id_str in self.users_in_admin_panel:
                self._remove_user_from_admin_panel(user_id_str)
            self._handle_start(message)
            return
        
        # Handle admin panel button
        if text == '🔐 Админ-панель' and self.is_admin(message.from_user.id):
            self._add_user_to_admin_panel(str(message.from_user.id))
            self.admin_panel.show_main_menu(message)
            return

        # Handle admin menu buttons (only if user is in admin panel context)
        user_id_str = str(message.from_user.id)
        if self.is_admin(message.from_user.id) and user_id_str in self.users_in_admin_panel:
            # User is in admin panel - route admin buttons to admin handler
            if text in ['👥 Участники', '🏆 Челленджи', '🎉 События', '📊 Статистика', '🔍 Модерация', '📤 Экспорт', '⚙️ Настройки']:
                logger.info(f"Admin {message.from_user.id} clicked '{text}' button in admin panel context")
                self.admin_panel.handle_admin_command(message)
                return
        
        # Handle user buttons (only if NOT in admin context)
        if text in ['🏃 Регистрация', 'регистрация на забег']:
            self._handle_registration(message)
        elif text == '🎉 События':
            logger.info(f"User {message.from_user.id} clicked Events button in main menu")
            self._handle_show_events(message)
        elif text == '🏆 Челленджи':
            logger.info(f"User {message.from_user.id} clicked Challenges button in main menu")
            self._handle_show_challenges(message)
        elif text == '📊 Статистика':
            self._handle_show_stats(message)
        elif text == 'ℹ️ Помощь':
            self._handle_help(message)
        else:
            # Generic response
            self.bot.reply_to(message, "Используйте команды меню или введите /help для получения помощи.")
    
    def start(self):
        """Start the bot"""
        logger.info("Initializing database...")
        self.db_manager.init_database()

        # Send startup notification to admins
        self._send_startup_notification()

        logger.info("Starting RunBot...")
        try:
            self.bot.polling(none_stop=True, interval=0, timeout=20)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            raise

    def _send_startup_notification(self):
        """Send notification to admins when bot starts"""
        try:
            from src.utils.startup_notification import send_first_launch_notification

            # Always send detailed notification (as requested by user)
            logger.info("📨 Sending comprehensive startup notification...")
            send_first_launch_notification(self.bot, self.admin_ids)

            logger.info("✅ Startup notifications sent to all admins")
        except Exception as e:
            logger.error(f"Error sending startup notifications: {e}")
    
    def stop(self):
        """Stop the bot"""
        logger.info("Stopping RunBot...")
        self.bot.stop_polling()


if __name__ == "__main__":
    """Entry point when running src/bot/main.py directly"""
    from dotenv import load_dotenv

    # Load environment variables
    load_dotenv()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create and start bot
    bot = RunBot()

    try:
        logging.info("🚀 Starting RunBot from src/bot/main.py...")
        bot.start()
    except KeyboardInterrupt:
        logging.info("🛑 Stopping bot...")
        bot.stop()
    except Exception as e:
        logging.error(f"❌ Error starting bot: {e}")
        raise