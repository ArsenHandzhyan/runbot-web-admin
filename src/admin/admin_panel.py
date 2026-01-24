"""
Admin Panel - Fixed Version with Complete Challenge Creation
"""

import telebot
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
import logging
import io
import re

from src.models.models import (
    Participant, Challenge, Submission, AdminAction, 
    DistanceType, ChallengeType, SubmissionStatus,
    Event, EventRegistration, EventStatus, EventType
)
from src.database.db import DatabaseManager
from src.utils.telegram_retry import safe_send_message

logger = logging.getLogger(__name__)

class AdminPanel:
    """Admin panel for managing the bot"""
    
    def __init__(self, bot: telebot.TeleBot, db_manager: DatabaseManager, admin_id: str, remove_user_from_admin_panel_func=None):
        self.bot = bot
        self.db_manager = db_manager
        self.admin_id = admin_id
        self.remove_user_from_admin_panel = remove_user_from_admin_panel_func
        self.active_admin_sessions = {}  # For multi-step admin operations

    def _send_media_file(self, chat_id: int, submission):
        """Helper to send media file from submission to Telegram"""
        if not submission.media_path:
            logger.info(f"No media file for submission {submission.id}")
            return False

        try:
            from src.utils.storage import get_storage_manager
            import mimetypes

            storage = get_storage_manager()
            file_data = storage.download_file(submission.media_path)

            if not file_data:
                logger.error(f"Failed to download media file: {submission.media_path}")
                safe_send_message(self.bot, chat_id, "⚠️ Не удалось загрузить медиа файл")
                return False

            # Determine file type from extension
            filename = submission.media_path.split('/')[-1]
            file_extension = filename.split('.')[-1].lower() if '.' in filename else ''

            # Create BytesIO object for Telegram
            file_io = io.BytesIO(file_data)
            file_io.name = filename

            logger.info(f"Sending media file: {filename}, type: {file_extension}, size: {len(file_data)} bytes")

            # Send based on file type
            if file_extension in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
                self.bot.send_photo(chat_id, file_io)
            elif file_extension in ['mp4', 'avi', 'mov', 'webm']:
                self.bot.send_video(chat_id, file_io)
            else:
                self.bot.send_document(chat_id, file_io)

            logger.info(f"✅ Media file sent successfully: {filename}")
            return True

        except Exception as e:
            logger.error(f"Error sending media file: {e}", exc_info=True)
            safe_send_message(self.bot, chat_id, "⚠️ Ошибка при отправке медиа файла")
            return False

    def _create_admin_keyboard(self):
        """Create persistent admin navigation keyboard"""
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        markup.row('👥 Участники', '🏆 Челленджи', '🎉 События')
        markup.row('📊 Статистика', '🔍 Модерация')
        markup.row('📤 Экспорт', '⚙️ Настройки')
        markup.row('🏠 Главное меню')
        return markup

    def _create_cancel_keyboard(self):
        """Create keyboard with cancel button"""
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
        markup.row('❌ Отменить')
        return markup

    def _cancel_admin_session(self, chat_id: int, message: str = "Операция отменена"):
        """Cancel active admin session and return to admin menu"""
        if chat_id in self.active_admin_sessions:
            del self.active_admin_sessions[chat_id]

        markup = self._create_admin_keyboard()
        safe_send_message(self.bot, chat_id, f"✅ {message}", reply_markup=markup)

    def show_main_menu(self, message):
        """Show main admin menu with persistent keyboard"""
        markup = self._create_admin_keyboard()

        # Send admin panel header with persistent keyboard
        if hasattr(message, 'chat') and hasattr(message.chat, 'id'):
            safe_send_message(self.bot, 
                message.chat.id,
                "*🔐 АДМИН-ПАНЕЛЬ RUNBOT*\n\n"
                "Добро пожаловать в систему управления!\n"
                "Используйте кнопки ниже для навигации:",
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            logger.error("Invalid message object passed to show_main_menu")
    
    def handle_admin_command(self, message):
        """Handle admin commands from button presses"""
        text = message.text
        chat_id = message.chat.id
        
        print(f"🔧 ADMIN COMMAND RECEIVED: '{text}' from {chat_id}")
        
        if text == '👥 Участники':
            self._show_participants_menu(message)
        elif text == '🏆 Челленджи':
            self._show_challenges_menu(message)
        elif text == '🎉 События':
            self._show_events_menu(message)
        elif text == '📊 Статистика':
            self._show_statistics_menu(message)
        elif text == '🔍 Модерация':
            self._show_moderation_menu(message)
        elif text == '📤 Экспорт':
            self._show_export_menu(message)
        elif text == '⚙️ Настройки':
            self._show_settings_menu(message)
        elif text == '🏠 Главное меню':
            # Return to user main menu instead of admin main menu
            # Remove user from admin panel tracking
            if self.remove_user_from_admin_panel:
                self.remove_user_from_admin_panel(str(chat_id))
            # Create proper message object for user menu
            fake_message = type('obj', (object,), {
                'chat': type('obj', (object,), {'id': chat_id})(),
                'from_user': type('obj', (object,), {'id': chat_id})()
            })()
            # This will trigger the main bot's send_welcome function
            # which shows user-style menu for admins too
            return
        else:
            print(f"❓ Unknown admin command: '{text}'")
    
    def _show_participants_menu(self, message):
        """Show participants management menu with choice between Events and Challenges"""
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🎉 По Событиям", callback_data="participants_events"),
            telebot.types.InlineKeyboardButton("🏆 По Челленджам", callback_data="participants_challenges")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("📋 Все участники", callback_data="list_participants")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
        )

        # Use send_message instead of reply_to to avoid message_id requirement
        if hasattr(message, 'chat') and hasattr(message.chat, 'id'):
            safe_send_message(self.bot, 
                message.chat.id,
                "*👥 Управление участниками*\n\n"
                "Выберите способ просмотра:\n\n"
                "🎉 *По Событиям* - участники конкретных забегов и турниров\n"
                "🏆 *По Челленджам* - участники активных челленджей\n"
                "📋 *Все участники* - полный список зарегистрированных",
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            logger.error("Invalid message object passed to _show_participants_menu")

    def _show_events_for_participants(self, chat_id):
        """Show list of events to choose from for viewing participants"""
        db = self.db_manager.get_session()
        try:
            from src.models.models import Event, EventStatus, EventType, EventRegistration

            # Get all events
            events = db.query(Event).filter(
                Event.is_active == True
            ).order_by(Event.start_date.desc()).all()

            if not events:
                safe_send_message(self.bot, chat_id, "❌ Событий пока нет")
                return

            markup = telebot.types.InlineKeyboardMarkup()

            for event in events:
                # Count participants
                participant_count = db.query(EventRegistration).filter(
                    EventRegistration.event_id == event.id
                ).count()

                # Event type emoji
                type_emoji = {
                    EventType.RUN_EVENT: "🏃",
                    EventType.TOURNAMENT: "🏅"
                }.get(event.event_type, "📅")

                # Status emoji
                status_emoji = {
                    EventStatus.UPCOMING: "📅",
                    EventStatus.ACTIVE: "🟢",
                    EventStatus.FINISHED: "🏁",
                    EventStatus.CANCELLED: "❌"
                }.get(event.status, "❓")

                button_text = f"{type_emoji} {event.name} ({participant_count} чел.) {status_emoji}"
                markup.row(
                    telebot.types.InlineKeyboardButton(
                        button_text,
                        callback_data=f"event_participants_{event.id}"
                    )
                )

            markup.row(
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="participants_menu")
            )

            safe_send_message(self.bot, 
                chat_id,
                "*🎉 Выберите событие для просмотра участников:*",
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error showing events for participants: {e}")
            safe_send_message(self.bot, chat_id, "❌ Ошибка при загрузке событий")
        finally:
            db.close()

    def _show_challenges_for_participants(self, chat_id):
        """Show list of challenges to choose from for viewing participants"""
        db = self.db_manager.get_session()
        try:
            from src.models.models import Challenge, ChallengeType
            from datetime import datetime

            # Get all challenges
            challenges = db.query(Challenge).filter(
                Challenge.is_active == True
            ).order_by(Challenge.end_date.desc()).all()

            if not challenges:
                safe_send_message(self.bot, chat_id, "❌ Челленджей пока нет")
                return

            markup = telebot.types.InlineKeyboardMarkup()

            for challenge in challenges:
                # Count participants (unique participants with submissions)
                from src.models.models import Submission, Participant
                participant_count = db.query(Participant.id).join(Submission).filter(
                    Submission.challenge_id == challenge.id
                ).distinct().count()

                # Challenge type emoji
                type_emoji = {
                    ChallengeType.PUSH_UPS: "💪",
                    ChallengeType.SQUATS: "🦵",
                    ChallengeType.PLANK: "🧘",
                    ChallengeType.RUNNING: "🏃",
                    ChallengeType.STEPS: "👣"
                }.get(challenge.challenge_type, "🏆")

                # Status
                is_active = challenge.end_date >= datetime.now()
                status_emoji = "🟢" if is_active else "🏁"

                button_text = f"{type_emoji} {challenge.name} ({participant_count} чел.) {status_emoji}"
                markup.row(
                    telebot.types.InlineKeyboardButton(
                        button_text,
                        callback_data=f"challenge_participants_{challenge.id}"
                    )
                )

            markup.row(
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="participants_menu")
            )

            safe_send_message(self.bot, 
                chat_id,
                "*🏆 Выберите челлендж для просмотра участников:*",
                parse_mode='Markdown',
                reply_markup=markup
            )
        except Exception as e:
            logger.error(f"Error showing challenges for participants: {e}")
            safe_send_message(self.bot, chat_id, "❌ Ошибка при загрузке челленджей")
        finally:
            db.close()

    def _show_challenges_menu(self, message):
        """Show challenges management menu with inline buttons only"""
        print("🔧 DEBUG: _show_challenges_menu called")
        print(f"🔧 DEBUG: message type: {type(message)}")
        print(f"🔧 DEBUG: message.chat.id: {getattr(getattr(message, 'chat', None), 'id', 'None')}")
        
        # Send challenges menu WITHOUT reply keyboard (use inline buttons only)
        message_text = (
            "*🏆 УПРАВЛЕНИЕ ЧЕЛЛЕНДЖАМИ*\n\n"
            "Создавайте и управляйте спортивными челленджами\n\n"
            "Доступные действия:"
        )
        
        # Create inline keyboard (these work correctly)
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("➕ Создать челлендж", callback_data="create_challenge"),
            telebot.types.InlineKeyboardButton("📋 Все челленджи", callback_data="list_challenges")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
        )
        
        # Send message with inline buttons only
        if hasattr(message, 'chat') and hasattr(message.chat, 'id'):
            safe_send_message(self.bot, 
                message.chat.id,
                message_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            print("✅ Admin challenges menu sent with inline buttons only")
        else:
            logger.error("Invalid message object passed to _show_challenges_menu")
            print("❌ Failed to send admin challenges menu")
    
    def _show_events_menu(self, message):
        """Show events management menu with inline buttons only"""
        print("🔧 DEBUG: _show_events_menu called")
        print(f"🔧 DEBUG: message type: {type(message)}")
        print(f"🔧 DEBUG: message.chat.id: {getattr(getattr(message, 'chat', None), 'id', 'None')}")
        
        # Send events menu WITHOUT reply keyboard (use inline buttons only)
        message_text = (
            "*🎉 УПРАВЛЕНИЕ СОБЫТИЯМИ*\n\n"
            "Создавайте и управляйте спортивными событиями\n\n"
            "Доступные действия:"
        )
        
        # Create inline keyboard (these work correctly)
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("➕ Создать событие", callback_data="create_event"),
            telebot.types.InlineKeyboardButton("📋 Все события", callback_data="list_events")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
        )
        
        # Send message with inline buttons only
        if hasattr(message, 'chat') and hasattr(message.chat, 'id'):
            safe_send_message(self.bot, 
                message.chat.id,
                message_text,
                parse_mode='Markdown',
                reply_markup=markup
            )
            print("✅ Admin events menu sent with inline buttons only")
        else:
            logger.error("Invalid message object passed to _show_events_menu")
            print("❌ Failed to send admin events menu")
    
    def _show_statistics_menu(self, message):
        """Show statistics menu"""
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📈 Общая статистика", callback_data="general_stats"),
            telebot.types.InlineKeyboardButton("🏅 Рейтинги", callback_data="leaderboard")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("📆 За период", callback_data="period_stats"),
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
        )
        
        # Use send_message instead of reply_to to avoid message_id requirement
        if hasattr(message, 'chat') and hasattr(message.chat, 'id'):
            safe_send_message(self.bot, 
                message.chat.id,
                "*📊 Статистика*\n\n"
                "• Общая статистика по всем участникам\n"
                "• Рейтинги и лидерборды\n"
                "• Статистика за выбранный период",
                parse_mode='Markdown',
                reply_markup=markup
            )
        else:
            logger.error("Invalid message object passed to _show_statistics_menu")
    
    def start_challenge_creation(self, chat_id: int):
        """Start challenge creation process"""
        logger.info(f"🎯 Starting challenge creation for admin {chat_id}")
        self.active_admin_sessions[chat_id] = {
            'context': 'admin',  # Mark as admin context
            'step': 'challenge_name',
            'data': {}
        }

        markup = self._create_cancel_keyboard()
        safe_send_message(self.bot, 
            chat_id,
            "📝 *Создание нового челленджа*\n\nВведите название челленджа:",
            parse_mode='Markdown',
            reply_markup=markup
        )
    
    def start_event_creation(self, chat_id: int):
        """Start event creation process"""
        logger.info(f"🎉 Starting event creation for admin {chat_id}")
        self.active_admin_sessions[chat_id] = {
            'context': 'admin',  # Mark as admin context
            'step': 'event_name',
            'data': {}
        }

        markup = self._create_cancel_keyboard()
        safe_send_message(self.bot, 
            chat_id,
            "📝 *Создание нового события*\n\nВведите название события:",
            parse_mode='Markdown',
            reply_markup=markup
        )
    
    def handle_event_creation_text(self, message):
        """Handle text input during event creation"""
        chat_id = message.chat.id
        text = message.text.strip()

        if chat_id not in self.active_admin_sessions:
            return

        # Check for cancellation
        if text in ['❌ Отменить', 'Отменить', '/cancel']:
            self._cancel_admin_session(chat_id, "Создание события отменено")
            return

        session_data = self.active_admin_sessions[chat_id]
        step = session_data['step']

        try:
            if step == 'event_name':
                if len(text) < 3:
                    safe_send_message(self.bot, chat_id, "Название должно быть не менее 3 символов")
                    return
                
                self.active_admin_sessions[chat_id]['data']['name'] = text
                self.active_admin_sessions[chat_id]['step'] = 'event_description'
                markup = self._create_cancel_keyboard()
                safe_send_message(self.bot, chat_id, "Введите описание события:", reply_markup=markup)
                
            elif step == 'event_description':
                self.active_admin_sessions[chat_id]['data']['description'] = text
                self.active_admin_sessions[chat_id]['step'] = 'event_type'

                # Show event type selection (только Забег и Турнир)
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.row('🏃 Забег', '🏅 Турнир')
                markup.row('❌ Отменить')

                safe_send_message(self.bot, 
                    chat_id,
                    "Выберите тип события:",
                    reply_markup=markup
                )

            elif step == 'event_type':
                # Map text to event type (убрали челлендж)
                type_mapping = {
                    'забег': 'run_event',
                    'турнир': 'tournament'
                }

                event_type_str = None
                text_lower = text.lower()

                for key, value in type_mapping.items():
                    if key in text_lower:
                        event_type_str = value
                        break

                if not event_type_str:
                    safe_send_message(self.bot, chat_id, "Пожалуйста, выберите один из предложенных типов")
                    return

                from src.models.models import EventType
                self.active_admin_sessions[chat_id]['data']['event_type'] = EventType(event_type_str)

                # Для всех типов событий сразу переходим к датам
                # Забег автоматически включает обе дистанции (детскую и взрослую)
                self.active_admin_sessions[chat_id]['step'] = 'event_start_date'
                markup = self._create_cancel_keyboard()
                safe_send_message(self.bot, 
                    chat_id,
                    "Введите дату начала в формате ДД.ММ.ГГГГ (например: 15.01.2026):",
                    reply_markup=markup
                )

            elif step == 'event_start_date':
                try:
                    from datetime import datetime
                    start_date = datetime.strptime(text, "%d.%m.%Y")
                    
                    if start_date.date() < datetime.now().date():
                        safe_send_message(self.bot, chat_id, "Дата начала не может быть в прошлом!")
                        return
                    
                    self.active_admin_sessions[chat_id]['data']['start_date'] = start_date
                    self.active_admin_sessions[chat_id]['step'] = 'event_end_date'

                    markup = self._create_cancel_keyboard()
                    safe_send_message(self.bot, 
                        chat_id,
                        "Введите дату окончания в формате ДД.ММ.ГГГГ (например: 30.01.2026):",
                        reply_markup=markup
                    )
                    
                except ValueError:
                    safe_send_message(self.bot, chat_id, "Неверный формат даты. Используйте ДД.ММ.ГГГГ")
                    
            elif step == 'event_end_date':
                try:
                    from datetime import datetime
                    end_date = datetime.strptime(text, "%d.%m.%Y")
                    start_date = self.active_admin_sessions[chat_id]['data']['start_date']

                    # Allow same day events (end_date >= start_date instead of end_date > start_date)
                    if end_date.date() < start_date.date():
                        safe_send_message(self.bot, chat_id, "Дата окончания не может быть раньше даты начала!")
                        return

                    self.active_admin_sessions[chat_id]['data']['end_date'] = end_date
                    self.active_admin_sessions[chat_id]['step'] = 'event_confirm'

                    # Show confirmation with event details
                    data = self.active_admin_sessions[chat_id]['data']

                    # Map event type to Russian
                    from src.models.models import EventType
                    event_type_display = {
                        EventType.RUN_EVENT: 'Забег',
                        EventType.TOURNAMENT: 'Турнир'
                    }.get(data['event_type'], str(data['event_type']))

                    # Build confirmation text
                    confirm_text = (
                        "Проверьте данные нового события:\n\n"
                        f"🎯 Название: {data['name']}\n"
                        f"📝 Описание: {data['description']}\n"
                        f"🏃 Тип: {event_type_display}\n"
                        f"📅 Начало: {data['start_date'].strftime('%d.%m.%Y')}\n"
                        f"📅 Окончание: {data['end_date'].strftime('%d.%m.%Y')}\n\n"
                        "Создать событие? Ответьте 'Да' или 'Нет'"
                    )

                    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                    markup.row('✅ Да', '❌ Нет')

                    safe_send_message(self.bot, chat_id, confirm_text, reply_markup=markup)

                except ValueError:
                    safe_send_message(self.bot, chat_id, "Неверный формат даты. Используйте ДД.ММ.ГГГГ")

            elif step == 'event_confirm':
                if 'да' in text.lower():
                    self._create_event(chat_id)
                elif 'нет' in text.lower():
                    del self.active_admin_sessions[chat_id]
                    # Return to events menu
                    message_obj = type('Message', (), {'chat': type('Chat', (), {'id': chat_id})})()
                    self._show_events_menu(message_obj)
                else:
                    safe_send_message(self.bot, chat_id, "Пожалуйста, ответьте 'Да' или 'Нет'")
                    
        except Exception as e:
            logger.error(f"Error in event creation: {e}")
            safe_send_message(self.bot, chat_id, f"Произошла ошибка: {str(e)}")
            # Clean up session on error
            if chat_id in self.active_admin_sessions:
                del self.active_admin_sessions[chat_id]
    
    def handle_challenge_creation_text(self, message):
        """Handle text input during challenge creation"""
        chat_id = message.chat.id
        text = message.text.strip()

        if chat_id not in self.active_admin_sessions:
            return

        # Check for cancellation
        if text in ['❌ Отменить', 'Отменить', '/cancel']:
            self._cancel_admin_session(chat_id, "Создание челленджа отменено")
            return

        session_data = self.active_admin_sessions[chat_id]
        step = session_data['step']

        try:
            if step == 'challenge_name':
                if len(text) < 3:
                    safe_send_message(self.bot, chat_id, "Название должно быть не менее 3 символов")
                    return
                
                self.active_admin_sessions[chat_id]['data']['name'] = text
                self.active_admin_sessions[chat_id]['step'] = 'challenge_description'
                markup = self._create_cancel_keyboard()
                safe_send_message(self.bot, chat_id, "Введите описание челленджа:", reply_markup=markup)
                
            elif step == 'challenge_description':
                self.active_admin_sessions[chat_id]['data']['description'] = text
                self.active_admin_sessions[chat_id]['step'] = 'challenge_type'
                
                # Show challenge type selection
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.row('💪 Отжимания', '🦵 Приседания')
                markup.row('🧘 Планка', '🏃 Бег')
                markup.row('👣 Шаги')
                markup.row('❌ Отменить')

                safe_send_message(self.bot, 
                    chat_id,
                    "Выберите тип челленджа:",
                    reply_markup=markup
                )
                
            elif step == 'challenge_type':
                # Map text to challenge type
                type_mapping = {
                    'отжимания': ChallengeType.PUSH_UPS,
                    'приседания': ChallengeType.SQUATS,
                    'планка': ChallengeType.PLANK,
                    'бег': ChallengeType.RUNNING,
                    'шаги': ChallengeType.STEPS
                }
                
                challenge_type = None
                text_lower = text.lower()
                
                for key, value in type_mapping.items():
                    if key in text_lower:
                        challenge_type = value
                        break
                
                if not challenge_type:
                    safe_send_message(self.bot, chat_id, "Пожалуйста, выберите один из предложенных типов")
                    return
                
                self.active_admin_sessions[chat_id]['data']['challenge_type'] = challenge_type
                self.active_admin_sessions[chat_id]['step'] = 'start_date'

                # Use cancel keyboard for date entry
                markup = self._create_cancel_keyboard()
                safe_send_message(self.bot, 
                    chat_id,
                    "Введите дату начала в формате ДД.ММ.ГГГГ (например: 15.01.2026):",
                    reply_markup=markup
                )
                
            elif step == 'start_date':
                try:
                    start_date = datetime.strptime(text, "%d.%m.%Y")
                    
                    if start_date.date() < datetime.now().date():
                        safe_send_message(self.bot, chat_id, "Дата начала не может быть в прошлом!")
                        return
                    
                    self.active_admin_sessions[chat_id]['data']['start_date'] = start_date
                    self.active_admin_sessions[chat_id]['step'] = 'end_date'

                    # Use cancel keyboard for date entry
                    markup = self._create_cancel_keyboard()

                    safe_send_message(self.bot, 
                        chat_id,
                        "Введите дату окончания в формате ДД.ММ.ГГГГ (например: 30.01.2026):",
                        reply_markup=markup
                    )
                    
                except ValueError:
                    safe_send_message(self.bot, chat_id, "Неверный формат даты. Используйте ДД.ММ.ГГГГ")
                    
            elif step == 'end_date':
                try:
                    end_date = datetime.strptime(text, "%d.%m.%Y")
                    start_date = self.active_admin_sessions[chat_id]['data']['start_date']
                    
                    # Allow same day events (end_date >= start_date instead of end_date > start_date)
                    if end_date.date() < start_date.date():
                        safe_send_message(self.bot, chat_id, "Дата окончания не может быть раньше даты начала!")
                        return
                    
                    self.active_admin_sessions[chat_id]['data']['end_date'] = end_date
                    self.active_admin_sessions[chat_id]['step'] = 'confirm'
                    
                    # Show confirmation
                    data = self.active_admin_sessions[chat_id]['data']
                    # Map challenge type to Russian
                    type_mapping = {
                        'push_ups': 'Отжимания',
                        'squats': 'Приседания', 
                        'plank': 'Планка',
                        'running': 'Бег',
                        'steps': 'Шаги'
                    }
                    challenge_type_display = type_mapping.get(data['challenge_type'].value, data['challenge_type'].value)
                    
                    confirm_text = (
                        "Проверьте данные нового челленджа:\n\n"
                        f"🎯 Название: {data['name']}\n"
                        f"📝 Описание: {data['description']}\n"
                        f"🔢 Тип: {challenge_type_display}\n"
                        f"📅 Начало: {data['start_date'].strftime('%d.%m.%Y')}\n"
                        f"📅 Окончание: {data['end_date'].strftime('%d.%m.%Y')}\n\n"
                        "Создать челлендж? Ответьте 'Да' или 'Нет'"
                    )
                    
                    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                    markup.row('✅ Да', '❌ Нет')
                    
                    safe_send_message(self.bot, chat_id, confirm_text, reply_markup=markup)
                    
                except ValueError:
                    safe_send_message(self.bot, chat_id, "Неверный формат даты. Используйте ДД.ММ.ГГГГ")
                    
            elif step == 'confirm':
                if 'да' in text.lower():
                    self._create_challenge(chat_id)
                elif 'нет' in text.lower():
                    del self.active_admin_sessions[chat_id]
                    # Return to challenges menu
                    message_obj = type('Message', (), {'chat': type('Chat', (), {'id': chat_id})})()
                    self._show_challenges_menu(message_obj)
                else:
                    safe_send_message(self.bot, chat_id, "Пожалуйста, ответьте 'Да' или 'Нет'")
                    
        except Exception as e:
            logger.error(f"Challenge creation error: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при создании челленджа")
            if chat_id in self.active_admin_sessions:
                del self.active_admin_sessions[chat_id]
    
    def _create_challenge(self, chat_id: int):
        """Create the challenge in database"""
        data = self.active_admin_sessions[chat_id]['data']

        db = self.db_manager.get_session()
        try:
            challenge = Challenge(
                name=data['name'],
                description=data['description'],
                challenge_type=data['challenge_type'],
                start_date=data['start_date'],
                end_date=data['end_date'],
                is_active=True
            )

            db.add(challenge)
            db.commit()
            db.refresh(challenge)  # Refresh to ensure data is persisted

            logger.info(f"New challenge created: {data['name']} with ID {challenge.id}")

            # Create success message with persistent admin keyboard
            admin_markup = self._create_admin_keyboard()

            safe_send_message(self.bot, 
                chat_id,
                f"✅ Челлендж успешно создан!\n\n"
                f"Название: {data['name']}\n"
                f"ID: {challenge.id}",
                reply_markup=admin_markup
            )

            # Clean up session first
            if chat_id in self.active_admin_sessions:
                del self.active_admin_sessions[chat_id]

            # Show admin menu after successful creation
            # Create a proper message object for menu display
            fake_message = type('obj', (object,), {
                'chat': type('obj', (object,), {'id': chat_id})(),
                'from_user': type('obj', (object,), {'id': int(self.admin_id)})()
            })()
            self._show_challenges_menu(fake_message)

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating challenge: {e}")
            logger.error(f"Challenge data: {data}")
            # Send detailed error message
            error_msg = f"Ошибка при создании челленджа:\n{str(e)}"
            safe_send_message(self.bot, chat_id, error_msg)
        finally:
            db.close()
            if chat_id in self.active_admin_sessions:
                del self.active_admin_sessions[chat_id]

    def _create_event(self, chat_id: int):
        """Create the event in database"""
        data = self.active_admin_sessions[chat_id]['data']

        from src.utils.event_manager import EventManager

        event_manager = EventManager(self.bot, self.db_manager)

        # Создаём событие без указания дистанции
        # Для забегов автоматически включаются обе дистанции (детская и взрослая)
        success = event_manager.create_event(
            name=data['name'],
            event_type=data['event_type'],
            start_date=data['start_date'],
            end_date=data['end_date'],
            description=data['description']
        )

        # Create persistent admin keyboard
        admin_markup = self._create_admin_keyboard()

        if success:
            safe_send_message(self.bot, 
                chat_id,
                f"✅ Событие успешно создано!\n\nНазвание: {data['name']}",
                reply_markup=admin_markup
            )
            logger.info(f"New event created: {data['name']} ({data['event_type'].value})")

            # Clean up session first
            if chat_id in self.active_admin_sessions:
                del self.active_admin_sessions[chat_id]

            # Show events menu after successful creation
            fake_message = type('obj', (object,), {
                'chat': type('obj', (object,), {'id': chat_id})(),
                'from_user': type('obj', (object,), {'id': int(self.admin_id)})()
            })()
            self._show_events_menu(fake_message)
        else:
            safe_send_message(self.bot, chat_id, "❌ Ошибка при создании события", reply_markup=admin_markup)
            # Clean up session on error
            if chat_id in self.active_admin_sessions:
                del self.active_admin_sessions[chat_id]
            # Show events menu even on error
            fake_message = type('obj', (object,), {
                'chat': type('obj', (object,), {'id': chat_id})(),
                'from_user': type('obj', (object,), {'id': int(self.admin_id)})()
            })()
            self._show_events_menu(fake_message)

    def handle_callback_query(self, call):
        """Handle callback queries from admin panel"""
        # FORCE PRINT - This MUST appear if method is entered
        print("==========================================")
        print("ADMIN PANEL HANDLE_CALLBACK_QUERY ENTERED")
        print("==========================================")
        print(f"call type: {type(call)}")
        print(f"call.data: {getattr(call, 'data', 'NO DATA')}")
        
        try:
            data = call.data
            # SIMPLE and WORKING way to get chat_id (from original working code)
            chat_id = call.from_user.id  # This always works for callback queries
            
            print(f"🔧 Admin panel received callback: {data} from chat {chat_id}")
            logger.info(f"Admin panel received callback: {data} from chat {chat_id}")
            
            print(f"🔧 Admin panel received callback: {data} from chat {chat_id}")
            logger.info(f"Admin panel received callback: {data} from chat {chat_id}")
            
            # Route to appropriate handler
            if data == 'list_participants':
                self.show_participants_list(chat_id)
            elif data == 'participants_events':
                self._show_events_for_participants(chat_id)
            elif data == 'participants_challenges':
                self._show_challenges_for_participants(chat_id)
            elif data == 'participants_menu':
                # Create fake message object to show participants menu
                fake_msg = type('obj', (object,), {
                    'chat': type('obj', (object,), {'id': chat_id})()
                })()
                self._show_participants_menu(fake_msg)
            elif data == 'participants_adult':
                self.show_participants_list(chat_id, 'adult')
            elif data == 'participants_children':
                self.show_participants_list(chat_id, 'children')
            elif data == 'participants_all':
                self.show_participants_list(chat_id)
            elif data == 'admin_participants':
                if call.message:
                    self._show_participants_menu(call.message)
            elif data == 'create_challenge':
                self.start_challenge_creation(chat_id)
            elif data == 'create_event':
                self.start_event_creation(chat_id)
            elif data == 'list_challenges':
                self.show_challenges_list(chat_id)
            elif data == 'list_events':
                self.show_events_list(chat_id)
            elif data == 'admin_challenges':
                if call.message:
                    self._show_challenges_menu(call.message)
            elif data == 'admin_events':
                if call.message:
                    self._show_events_menu(call.message)
            elif data == 'general_stats':
                self.show_general_statistics(chat_id)
            elif data == 'moderate_pending':
                self.show_pending_submissions(chat_id)
            elif data == 'all_submissions':
                self.show_all_submissions(chat_id)
            elif data == 'export_menu_participants':
                self._show_export_participants_menu(chat_id)
            elif data == 'export_menu_events':
                self._show_export_events_menu(chat_id)
            elif data == 'export_menu_challenges':
                self._show_export_challenges_menu(chat_id)
            elif data == 'export_menu_submissions':
                self._show_export_submissions_menu(chat_id)
            elif data == 'export_menu_ratings':
                self._show_export_ratings_menu(chat_id)
            elif data == 'export_participants':
                self.export_participants_excel(chat_id)
            elif data == 'export_submissions':
                self.export_submissions_excel(chat_id)
            elif data == 'export_ratings':
                self.export_ratings_excel(chat_id)
            elif data.startswith('export_event_'):
                event_id = int(data.split('_')[-1])
                self.export_event_participants_excel(chat_id, event_id)
            elif data.startswith('export_challenge_'):
                challenge_id = int(data.split('_')[-1])
                self.export_challenge_participants_excel(chat_id, challenge_id)
            elif data == 'export_all_events':
                self.export_all_events_excel(chat_id)
            elif data == 'export_all_challenges':
                self.export_all_challenges_excel(chat_id)
            elif data.startswith('approve_'):
                submission_id = int(data.split('_')[1])
                if self.approve_submission(submission_id, str(chat_id)):
                    self.bot.answer_callback_query(call.id, "✅ Отчет одобрен!")
                    # Safely edit message if it exists
                    if call.message and hasattr(call.message, 'message_id'):
                        self.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=call.message.message_id,
                            text="✅ Отчет был одобрен",
                            reply_markup=None
                        )
                    else:
                        # Fallback: send new message
                        safe_send_message(self.bot, chat_id, "✅ Отчет был одобрен")
                else:
                    self.bot.answer_callback_query(call.id, "❌ Ошибка при одобрении")
            elif data.startswith('reject_'):
                submission_id = int(data.split('_')[1])
                if self.reject_submission(submission_id, str(chat_id)):
                    self.bot.answer_callback_query(call.id, "❌ Отчет отклонен!")
                    # Safely edit message if it exists
                    if call.message and hasattr(call.message, 'message_id'):
                        self.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=call.message.message_id,
                            text="❌ Отчет был отклонен",
                            reply_markup=None
                        )
                    else:
                        # Fallback: send new message
                        safe_send_message(self.bot, chat_id, "❌ Отчет был отклонен")
                else:
                    self.bot.answer_callback_query(call.id, "❌ Ошибка при отклонении")
            elif data == 'admin_main':
                if call.message:
                    self.show_main_menu(call.message)
            elif data == 'admin_statistics':
                if call.message:
                    self._show_statistics_menu(call.message)
            elif data == 'admin_moderation':
                if call.message:
                    self._show_moderation_menu(call.message)
            elif data == 'admin_export':
                if call.message:
                    self._show_export_menu(call.message)
            elif data == 'admin_settings':
                if call.message:
                    self._show_settings_menu(call.message)
            elif data == 'bot_status':
                self._show_bot_status(chat_id)
            elif data == 'db_status':
                self._show_db_status(chat_id)
            elif data.startswith('event_participants_'):
                event_id = int(data.split('_')[-1])
                self.show_event_participants(chat_id, event_id)
            elif data.startswith('challenge_participants_'):
                challenge_id = int(data.split('_')[-1])
                self.show_challenge_participants(chat_id, challenge_id)
            else:
                self.bot.answer_callback_query(call.id, "Функция в разработке")
                
        except Exception as e:
            print(f"❌ DEBUG: EXCEPTION in handle_callback_query: {e}")
            import traceback
            print(f"❌ DEBUG: TRACEBACK: {traceback.format_exc()}")
            logger.error(f"Callback handling error: {e}")
            self.bot.answer_callback_query(call.id, "Ошибка обработки запроса")
    
    def handle_text(self, message):
        """Handle text messages for admin sessions"""
        chat_id = message.chat.id
        text = message.text.strip()
        
        # Handle admin event creation flow
        if hasattr(self, 'active_admin_sessions'):
            if chat_id in self.active_admin_sessions:
                session_data = self.active_admin_sessions[chat_id]
                current_step = session_data.get('step', '')
                if current_step.startswith('event_') or current_step == 'event_confirm':
                    self.handle_event_creation_text(message)
                    return
        
        # Handle admin challenge creation flow
        if hasattr(self, 'active_admin_sessions'):
            if chat_id in self.active_admin_sessions:
                session_data = self.active_admin_sessions[chat_id]
                current_step = session_data.get('step', '')
                if current_step.startswith('challenge_') or current_step in ['start_date', 'end_date', 'confirm']:
                    self.handle_challenge_creation_text(message)
                    return
                elif current_step.startswith('event_'):
                    self.handle_event_creation_text(message)
                    return
        
        # Only delete session if it exists and no flows matched
        # This prevents premature session termination
        if chat_id in self.active_admin_sessions:
            session_data = self.active_admin_sessions[chat_id]
            current_step = session_data.get('step', '')
            
            # Log the issue for debugging
            logger.warning(f"Unhandled admin message from {chat_id} at step '{current_step}': '{text}'")
            
            # Don't automatically delete session - let user continue or manually cancel
            safe_send_message(self.bot, 
                chat_id, 
                f"Не удалось обработать сообщение на шаге '{current_step}'.\n"
                f"Пожалуйста, следуйте инструкциям или используйте главное меню."
            )
    
    def show_participants_list(self, chat_id: int, distance_filter: str = None):
        """Show list of participants with optional filtering"""
        db = self.db_manager.get_session()
        try:
            # Build query with optional filter
            query = db.query(Participant).filter(Participant.is_active == True)
            
            if distance_filter == 'adult':
                query = query.filter(Participant.distance_type == DistanceType.ADULT_RUN)
            elif distance_filter == 'children':
                query = query.filter(Participant.distance_type == DistanceType.CHILDREN_RUN)
            
            participants = query.order_by(Participant.registration_date.desc()).limit(50).all()
            
            if not participants:
                safe_send_message(self.bot, chat_id, "Список участников пуст")
                return
            
            # Create message
            message = "*👥 Список участников*\n\n"
            
            for i, participant in enumerate(participants[:20], 1):  # Show first 20
                distance_text = '🏃 Взрослый' if participant.distance_type == DistanceType.ADULT_RUN else '👶 Детский'
                message += (
                    f"{i}. `{participant.start_number}` - {participant.full_name}\n"
                    f"   📞 {participant.phone} | {distance_text}\n"
                    f"   📅 {participant.registration_date.strftime('%d.%m.%Y')}\n\n"
                )
            
            if len(participants) > 20:
                message += f"... и еще {len(participants) - 20} участников"
            
            # Add filter buttons
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("🚴 Взрослые", callback_data="participants_adult"),
                telebot.types.InlineKeyboardButton("👶 Детские", callback_data="participants_children")
            )
            markup.row(
                telebot.types.InlineKeyboardButton("📊 Все", callback_data="participants_all"),
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_participants")
            )
            
            safe_send_message(self.bot, chat_id, message, parse_mode='Markdown', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error showing participants: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении списка участников")
        finally:
            db.close()
    
    def show_challenges_list(self, chat_id: int):
        """Show list of all challenges"""
        db = self.db_manager.get_session()
        try:
            challenges = db.query(Challenge).order_by(Challenge.created_at.desc()).all()
            
            if not challenges:
                safe_send_message(self.bot, chat_id, "Нет созданных челленджей")
                return
            
            message = "*🏆 Список челленджей*\n\n"
            
            for challenge in challenges:
                status = "🟢 Активный" if challenge.is_active else "🔴 Неактивный"
                days_left = (challenge.end_date - datetime.now()).days if challenge.end_date > datetime.now() else 0
                
                message += (
                    f"🎯 *{challenge.name}*\n"
                    f"   {status} | {days_left} дней осталось\n"
                    f"   Тип: {'Отжимания' if challenge.challenge_type.value == 'push_ups' else 'Приседания' if challenge.challenge_type.value == 'squats' else 'Планка' if challenge.challenge_type.value == 'plank' else 'Бег' if challenge.challenge_type.value == 'running' else 'Шаги' if challenge.challenge_type.value == 'steps' else challenge.challenge_type.value}\n"
                    f"   Период: {challenge.start_date.strftime('%d.%m')} - {challenge.end_date.strftime('%d.%m')}\n\n"
                )
            
            # Add navigation buttons
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("➕ Создать", callback_data="create_challenge"),
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_challenges")
            )
            
            safe_send_message(self.bot, chat_id, message, parse_mode='Markdown', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error showing challenges: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении списка челленджей")
        finally:
            db.close()
    
    def show_events_list(self, chat_id: int):
        """Show list of all events"""
        from src.models.models import Event, EventType, EventStatus, EventRegistration
        db = self.db_manager.get_session()
        try:
            events = db.query(Event).order_by(Event.created_at.desc()).all()
            
            if not events:
                safe_send_message(self.bot, chat_id, "Нет созданных событий")
                return
            
            message = "*🎉 Список событий*\n\n"
            
            for event in events:
                # Event type display
                type_display = {
                    EventType.RUN_EVENT: "🏃 Забег",
                    EventType.CHALLENGE: "🏆 Челлендж",
                    EventType.TOURNAMENT: "🏅 Турнир"
                }.get(event.event_type, "❓")
                
                # Status display
                status_display = {
                    EventStatus.UPCOMING: "📅 Скоро",
                    EventStatus.ACTIVE: "🟢 Активно",
                    EventStatus.FINISHED: "🏁 Завершено",
                    EventStatus.CANCELLED: "❌ Отменено"
                }.get(event.status, "❓")
                
                # Registration info
                registration_count = db.query(EventRegistration).filter(
                    EventRegistration.event_id == event.id
                ).count()
                
                max_participants_info = f" / {event.max_participants}" if event.max_participants else ""
                
                message += (
                    f"{status_display} *{event.name}*\n"
                    f"   {type_display}\n"
                    f"   📅 {event.start_date.strftime('%d.%m.%Y')} - {event.end_date.strftime('%d.%m.%Y')}\n"
                    f"   👥 Участников: {registration_count}{max_participants_info}\n"
                )
                
                if event.description:
                    message += f"   📝 {event.description[:100]}...\n"
                
                message += "\n"
            
            # Add navigation buttons
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("➕ Создать", callback_data="create_event"),
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_events")
            )
            
            safe_send_message(self.bot, chat_id, message, parse_mode='Markdown', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error showing events: {e}")
            import traceback
            logger.error(traceback.format_exc())
            safe_send_message(self.bot, chat_id, f"Ошибка при получении списка событий: {str(e)}")
        finally:
            db.close()
    
    def show_general_statistics(self, chat_id: int):
        """Show general statistics"""
        db = self.db_manager.get_session()
        try:
            # Get counts
            total_participants = db.query(Participant).filter(Participant.is_active == True).count()
            adult_participants = db.query(Participant).filter(
                Participant.distance_type == DistanceType.ADULT_RUN,
                Participant.is_active == True
            ).count()
            children_participants = db.query(Participant).filter(
                Participant.distance_type == DistanceType.CHILDREN_RUN,
                Participant.is_active == True
            ).count()
            
            total_submissions = db.query(Submission).count()
            approved_submissions = db.query(Submission).filter(
                Submission.status == SubmissionStatus.APPROVED
            ).count()
            pending_submissions = db.query(Submission).filter(
                Submission.status == SubmissionStatus.PENDING
            ).count()
            
            active_challenges = db.query(Challenge).filter(Challenge.is_active == True).count()
            
            # Calculate percentages
            approval_rate = (approved_submissions / total_submissions * 100) if total_submissions > 0 else 0
            
            stats_text = (
                f"*📈 Общая статистика*\n\n"
                f"👥 *Участники:*\n"
                f"   Всего: {total_participants}\n"
                f"   Взрослые: {adult_participants}\n"
                f"   Детские: {children_participants}\n\n"
                f"🏆 *Челленджи:*\n"
                f"   Активных: {active_challenges}\n\n"
                f"📝 *Отчеты:*\n"
                f"   Всего: {total_submissions}\n"
                f"   Одобрено: {approved_submissions}\n"
                f"   На проверке: {pending_submissions}\n"
                f"   Процент одобрения: {approval_rate:.1f}%"
            )
            
            safe_send_message(self.bot, chat_id, stats_text, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing statistics: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении статистики")
        finally:
            db.close()
    
    def show_all_submissions(self, chat_id: int):
        """Show all submissions (approved, pending, rejected)"""
        db = self.db_manager.get_session()
        try:
            # Get all submissions with participant and challenge info
            submissions = db.query(Submission, Participant, Challenge).join(
                Participant, Submission.participant_id == Participant.id
            ).join(
                Challenge, Submission.challenge_id == Challenge.id
            ).order_by(Submission.submission_date.desc()).limit(10).all()

            if not submissions:
                safe_send_message(self.bot, chat_id, "Нет отчетов для отображения")
                return

            # Send each submission as a separate message with media
            for submission, participant, challenge in submissions:
                # Send media file if exists
                if submission.media_path:
                    self._send_media_file(chat_id, submission)

                status_icon = {
                    SubmissionStatus.PENDING: "⏳",
                    SubmissionStatus.APPROVED: "✅",
                    SubmissionStatus.REJECTED: "❌"
                }.get(submission.status, "❓")

                status_text = {
                    SubmissionStatus.PENDING: "На проверке",
                    SubmissionStatus.APPROVED: "Одобрено",
                    SubmissionStatus.REJECTED: "Отклонено"
                }.get(submission.status, "Неизвестно")

                message = (
                    f"*📊 Отчет #{submission.id}*\n\n"
                    f"{status_icon} Статус: *{status_text}*\n"
                    f"👤 Участник: {participant.full_name} (#{participant.start_number})\n"
                    f"🏆 Челлендж: {challenge.name}\n"
                    f"📊 Результат: {submission.result_value} {submission.result_unit}\n"
                    f"📅 Дата: {submission.submission_date.strftime('%d.%m.%Y %H:%M')}\n"
                )

                if submission.comment:
                    message += f"💬 Комментарий: {submission.comment}\n"

                if submission.media_path:
                    message += f"📎 Медиа: {submission.media_path.split('/')[-1]}\n"

                # Add moderation buttons if pending
                if submission.status == SubmissionStatus.PENDING:
                    markup = telebot.types.InlineKeyboardMarkup()
                    markup.row(
                        telebot.types.InlineKeyboardButton(
                            "✅ Одобрить",
                            callback_data=f"approve_{submission.id}"
                        ),
                        telebot.types.InlineKeyboardButton(
                            "❌ Отклонить",
                            callback_data=f"reject_{submission.id}"
                        )
                    )
                    safe_send_message(self.bot, chat_id, message, parse_mode='Markdown', reply_markup=markup)
                else:
                    safe_send_message(self.bot, chat_id, message, parse_mode='Markdown')

            # Add navigation buttons
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("⏳ На проверке", callback_data="moderate_pending"),
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
            )

            safe_send_message(self.bot, chat_id, "Выберите действие:", reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error showing all submissions: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении всех отчетов")
        finally:
            db.close()
    
    def show_pending_submissions(self, chat_id: int):
        """Show pending submissions for moderation"""
        db = self.db_manager.get_session()
        try:
            pending_submissions = db.query(Submission).filter(
                Submission.status == SubmissionStatus.PENDING
            ).order_by(Submission.submission_date.asc()).limit(10).all()
            
            if not pending_submissions:
                safe_send_message(self.bot, chat_id, "Нет отчетов на проверке")
                return
            
            for submission in pending_submissions:
                participant = db.query(Participant).get(submission.participant_id)
                challenge = db.query(Challenge).get(submission.challenge_id)

                # Send media file if exists
                if submission.media_path:
                    self._send_media_file(chat_id, submission)

                # Create moderation message
                message_text = (
                    f"*🔍 Отчет на проверку*\n\n"
                    f"👤 Участник: {participant.full_name} (#{participant.start_number})\n"
                    f"🏆 Челлендж: {challenge.name}\n"
                    f"📊 Результат: {submission.result_value} {submission.result_unit}\n"
                    f"📅 Дата: {submission.submission_date.strftime('%d.%m.%Y %H:%M')}\n"
                )

                if submission.comment:
                    message_text += f"💬 Комментарий: {submission.comment}\n"

                if submission.media_path:
                    message_text += f"📎 Медиа: {submission.media_path.split('/')[-1]}\n"

                # Add moderation buttons
                markup = telebot.types.InlineKeyboardMarkup()
                markup.row(
                    telebot.types.InlineKeyboardButton(
                        "✅ Одобрить",
                        callback_data=f"approve_{submission.id}"
                    ),
                    telebot.types.InlineKeyboardButton(
                        "❌ Отклонить",
                        callback_data=f"reject_{submission.id}"
                    )
                )

                safe_send_message(self.bot, chat_id, message_text, parse_mode='Markdown', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error showing pending submissions: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении отчетов на проверку")
        finally:
            db.close()
    
    def approve_submission(self, submission_id: int, admin_telegram_id: str, comment: str = None):
        """Approve a submission"""
        db = self.db_manager.get_session()
        try:
            submission = db.query(Submission).get(submission_id)
            if not submission:
                return False
            
            submission.status = SubmissionStatus.APPROVED
            if comment:
                submission.moderator_comment = comment
            
            # Log admin action
            action = AdminAction(
                admin_telegram_id=admin_telegram_id,
                action_type="approve",
                target_id=submission_id,
                details=f"Approved submission {submission_id}"
            )
            db.add(action)
            db.commit()
            
            logger.info(f"Submission {submission_id} approved by admin {admin_telegram_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error approving submission: {e}")
            return False
        finally:
            db.close()
    
    def reject_submission(self, submission_id: int, admin_telegram_id: str, comment: str = None):
        """Reject a submission"""
        db = self.db_manager.get_session()
        try:
            submission = db.query(Submission).get(submission_id)
            if not submission:
                return False
            
            submission.status = SubmissionStatus.REJECTED
            if comment:
                submission.moderator_comment = comment
            
            # Log admin action
            action = AdminAction(
                admin_telegram_id=admin_telegram_id,
                action_type="reject",
                target_id=submission_id,
                details=f"Rejected submission {submission_id}" + (f": {comment}" if comment else "")
            )
            db.add(action)
            db.commit()
            
            logger.info(f"Submission {submission_id} rejected by admin {admin_telegram_id}")
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error rejecting submission: {e}")
            return False
        finally:
            db.close()
    
    def export_participants_excel(self, chat_id: int):
        """Export participants list to Excel"""
        try:
            from src.utils.reports import ReportGenerator
            
            report_generator = ReportGenerator(self.db_manager)
            excel_file = report_generator.generate_participants_report()
            
            # Send file
            self.bot.send_document(
                chat_id,
                excel_file,
                caption="📋 Список участников (Excel)",
                visible_file_name="participants.xlsx"
            )
            
            logger.info(f"Participants export sent to admin {chat_id}")
            
        except Exception as e:
            logger.error(f"Error exporting participants: {e}")
            safe_send_message(self.bot, chat_id, f"❌ Ошибка экспорта: {str(e)}")
    
    def export_submissions_excel(self, chat_id: int):
        """Export submissions to Excel"""
        try:
            from src.utils.reports import ReportGenerator
            
            report_generator = ReportGenerator(self.db_manager)
            excel_file = report_generator.generate_submissions_report()
            
            self.bot.send_document(
                chat_id,
                excel_file,
                caption="📊 Отчеты участников (Excel)",
                visible_file_name="submissions.xlsx"
            )
            
            logger.info(f"Submissions export sent to admin {chat_id}")
            
        except Exception as e:
            logger.error(f"Error exporting submissions: {e}")
            safe_send_message(self.bot, chat_id, f"❌ Ошибка экспорта: {str(e)}")
    
    def export_ratings_excel(self, chat_id: int):
        """Export ratings/leaderboard to Excel"""
        try:
            from src.utils.reports import ReportGenerator
            
            report_generator = ReportGenerator(self.db_manager)
            excel_file = report_generator.generate_leaderboard_report()
            
            self.bot.send_document(
                chat_id,
                excel_file,
                caption="🏆 Рейтинг участников (Excel)",
                visible_file_name="leaderboard.xlsx"
            )
            
            logger.info(f"Leaderboard export sent to admin {chat_id}")
            
        except Exception as e:
            logger.error(f"Error exporting ratings: {e}")
            safe_send_message(self.bot, chat_id, f"❌ Ошибка экспорта: {str(e)}")

    def export_event_participants_excel(self, chat_id: int, event_id: int):
        """Export participants of a specific event to Excel"""
        try:
            from src.utils.reports import ReportGenerator

            db = self.db_manager.get_session()
            try:
                event = db.query(Event).filter(Event.id == event_id).first()
                if not event:
                    safe_send_message(self.bot, chat_id, "❌ Событие не найдено")
                    return

                report_generator = ReportGenerator(self.db_manager)
                excel_file = report_generator.generate_event_participants_report(event_id)

                self.bot.send_document(
                    chat_id,
                    excel_file,
                    caption=f"🎉 Участники события '{event.name}' (Excel)",
                    visible_file_name=f"event_{event_id}_participants.xlsx"
                )

                logger.info(f"Event {event_id} participants export sent to admin {chat_id}")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error exporting event participants: {e}")
            safe_send_message(self.bot, chat_id, f"❌ Ошибка экспорта: {str(e)}")

    def export_challenge_participants_excel(self, chat_id: int, challenge_id: int):
        """Export participants of a specific challenge to Excel"""
        try:
            from src.utils.reports import ReportGenerator

            db = self.db_manager.get_session()
            try:
                challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
                if not challenge:
                    safe_send_message(self.bot, chat_id, "❌ Челлендж не найден")
                    return

                report_generator = ReportGenerator(self.db_manager)
                excel_file = report_generator.generate_challenge_participants_report(challenge_id)

                self.bot.send_document(
                    chat_id,
                    excel_file,
                    caption=f"🏆 Участники челленджа '{challenge.name}' (Excel)",
                    visible_file_name=f"challenge_{challenge_id}_participants.xlsx"
                )

                logger.info(f"Challenge {challenge_id} participants export sent to admin {chat_id}")

            finally:
                db.close()

        except Exception as e:
            logger.error(f"Error exporting challenge participants: {e}")
            safe_send_message(self.bot, chat_id, f"❌ Ошибка экспорта: {str(e)}")

    def export_all_events_excel(self, chat_id: int):
        """Export all events with their participants to Excel"""
        try:
            from src.utils.reports import ReportGenerator

            report_generator = ReportGenerator(self.db_manager)
            excel_file = report_generator.generate_all_events_report()

            self.bot.send_document(
                chat_id,
                excel_file,
                caption="🎉 Все события с участниками (Excel)",
                visible_file_name="all_events.xlsx"
            )

            logger.info(f"All events export sent to admin {chat_id}")

        except Exception as e:
            logger.error(f"Error exporting all events: {e}")
            safe_send_message(self.bot, chat_id, f"❌ Ошибка экспорта: {str(e)}")

    def export_all_challenges_excel(self, chat_id: int):
        """Export all challenges with their participants to Excel"""
        try:
            from src.utils.reports import ReportGenerator

            report_generator = ReportGenerator(self.db_manager)
            excel_file = report_generator.generate_all_challenges_report()

            self.bot.send_document(
                chat_id,
                excel_file,
                caption="🏆 Все челленджи с участниками (Excel)",
                visible_file_name="all_challenges.xlsx"
            )

            logger.info(f"All challenges export sent to admin {chat_id}")

        except Exception as e:
            logger.error(f"Error exporting all challenges: {e}")
            safe_send_message(self.bot, chat_id, f"❌ Ошибка экспорта: {str(e)}")

    def _show_moderation_menu(self, message):
        """Show moderation menu"""
        db = self.db_manager.get_session()
        try:
            pending_count = db.query(Submission).filter(
                Submission.status == SubmissionStatus.PENDING
            ).count()
            
            message_text = (
                f"*🔍 Модерация*\n\n"
                f"⏳ Отчетов на проверке: {pending_count}\n\n"
                f"Выберите действие:"
            )
            
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton(f"📋 Проверить ({pending_count})", callback_data="moderate_pending"),
                telebot.types.InlineKeyboardButton("📊 Все отчеты", callback_data="all_submissions")
            )
            markup.row(
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
            )
            
            # Use send_message instead of reply_to to avoid message_id requirement
            if hasattr(message, 'chat') and hasattr(message.chat, 'id'):
                safe_send_message(self.bot, 
                    message.chat.id,
                    message_text,
                    parse_mode='Markdown',
                    reply_markup=markup
                )
            else:
                logger.error("Invalid message object passed to _show_moderation_menu")
            
        finally:
            db.close()
    
    def _show_export_menu(self, message):
        """Show export menu with flexible selection"""
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("👥 Участники", callback_data="export_menu_participants")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🎉 События", callback_data="export_menu_events"),
            telebot.types.InlineKeyboardButton("🏆 Челленджи", callback_data="export_menu_challenges")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("📊 Отчёты", callback_data="export_menu_submissions"),
            telebot.types.InlineKeyboardButton("📈 Рейтинги", callback_data="export_menu_ratings")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
        )

        self.bot.reply_to(
            message,
            "*📤 Экспорт данных*\n\n"
            "Выберите категорию для экспорта:\n\n"
            "👥 *Участники* - список всех зарегистрированных\n"
            "🎉 *События* - участники конкретных забегов/турниров\n"
            "🏆 *Челленджи* - участники конкретных челленджей\n"
            "📊 *Отчёты* - данные по отчётам участников\n"
            "📈 *Рейтинги* - таблица лидеров",
            parse_mode='Markdown',
            reply_markup=markup
        )

    def _show_export_participants_menu(self, chat_id: int):
        """Show participants export submenu"""
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📄 Все участники", callback_data="export_participants")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_export")
        )

        safe_send_message(self.bot, 
            chat_id,
            "*👥 Экспорт участников*\n\n"
            "📄 Полный список всех зарегистрированных участников с их данными и статистикой",
            parse_mode='Markdown',
            reply_markup=markup
        )

    def _show_export_events_menu(self, chat_id: int):
        """Show events export submenu with list of events"""
        db = self.db_manager.get_session()
        try:
            events = db.query(Event).filter(Event.is_active == True).order_by(Event.start_date.desc()).all()

            markup = telebot.types.InlineKeyboardMarkup()

            if events:
                markup.row(
                    telebot.types.InlineKeyboardButton("📋 Все события", callback_data="export_all_events")
                )

                for event in events[:15]:  # Limit to 15 events
                    participant_count = db.query(EventRegistration).filter(
                        EventRegistration.event_id == event.id
                    ).count()

                    type_emoji = {
                        EventType.RUN_EVENT: "🏃",
                        EventType.TOURNAMENT: "🏅"
                    }.get(event.event_type, "📅")

                    button_text = f"{type_emoji} {event.name} ({participant_count} чел.)"
                    markup.row(telebot.types.InlineKeyboardButton(
                        button_text,
                        callback_data=f"export_event_{event.id}"
                    ))

            markup.row(
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_export")
            )

            message_text = "*🎉 Экспорт по событиям*\n\n"
            if events:
                message_text += "Выберите событие для экспорта списка участников:"
            else:
                message_text += "Нет доступных событий для экспорта"

            safe_send_message(self.bot, 
                chat_id,
                message_text,
                parse_mode='Markdown',
                reply_markup=markup
            )

        finally:
            db.close()

    def _show_export_challenges_menu(self, chat_id: int):
        """Show challenges export submenu with list of challenges"""
        db = self.db_manager.get_session()
        try:
            challenges = db.query(Challenge).filter(
                Challenge.is_active == True
            ).order_by(Challenge.end_date.desc()).all()

            markup = telebot.types.InlineKeyboardMarkup()

            if challenges:
                markup.row(
                    telebot.types.InlineKeyboardButton("📋 Все челленджи", callback_data="export_all_challenges")
                )

                for challenge in challenges[:15]:  # Limit to 15 challenges
                    participant_count = db.query(Participant.id).join(Submission).filter(
                        Submission.challenge_id == challenge.id
                    ).distinct().count()

                    type_emoji = {
                        ChallengeType.PUSH_UPS: "💪",
                        ChallengeType.SQUATS: "🦵",
                        ChallengeType.PLANK: "🧘",
                        ChallengeType.RUNNING: "🏃",
                        ChallengeType.STEPS: "👣"
                    }.get(challenge.challenge_type, "🏆")

                    button_text = f"{type_emoji} {challenge.name} ({participant_count} чел.)"
                    markup.row(telebot.types.InlineKeyboardButton(
                        button_text,
                        callback_data=f"export_challenge_{challenge.id}"
                    ))

            markup.row(
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_export")
            )

            message_text = "*🏆 Экспорт по челленджам*\n\n"
            if challenges:
                message_text += "Выберите челлендж для экспорта списка участников:"
            else:
                message_text += "Нет доступных челленджей для экспорта"

            safe_send_message(self.bot, 
                chat_id,
                message_text,
                parse_mode='Markdown',
                reply_markup=markup
            )

        finally:
            db.close()

    def _show_export_submissions_menu(self, chat_id: int):
        """Show submissions export submenu"""
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("📊 Все отчёты", callback_data="export_submissions")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_export")
        )

        safe_send_message(self.bot, 
            chat_id,
            "*📊 Экспорт отчётов*\n\n"
            "📊 Полный список всех отчётов участников с результатами и статусами",
            parse_mode='Markdown',
            reply_markup=markup
        )

    def _show_export_ratings_menu(self, chat_id: int):
        """Show ratings export submenu"""
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🏆 Общий рейтинг", callback_data="export_ratings")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_export")
        )

        safe_send_message(self.bot, 
            chat_id,
            "*📈 Экспорт рейтингов*\n\n"
            "🏆 Таблица лидеров с баллами, отчётами и сериями дней",
            parse_mode='Markdown',
            reply_markup=markup
        )

    def _show_settings_menu(self, message):
        """Show settings menu"""
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🤖 Состояние бота", callback_data="bot_status"),
            telebot.types.InlineKeyboardButton("💾 База данных", callback_data="db_status")
        )
        markup.row(
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main")
        )

        self.bot.reply_to(
            message,
            "*⚙️ Настройки*\n\n"
            "• Проверка состояния системы\n"
            "• Мониторинг базы данных",
            parse_mode='Markdown',
            reply_markup=markup
        )

    def _show_bot_status(self, chat_id: int):
        """Show bot status information"""
        import datetime
        import psutil
        import os

        try:
            # Get process info
            process = psutil.Process(os.getpid())

            # Memory usage
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024

            # CPU usage
            cpu_percent = process.cpu_percent(interval=1)

            # Uptime
            create_time = datetime.datetime.fromtimestamp(process.create_time())
            uptime = datetime.datetime.now() - create_time
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)

            # Thread count
            thread_count = process.num_threads()

            message = (
                "*🤖 Состояние бота*\n\n"
                f"✅ Статус: Активен\n"
                f"⏱ Время работы: {hours}ч {minutes}м {seconds}с\n"
                f"💾 Память: {memory_mb:.1f} MB\n"
                f"⚡️ CPU: {cpu_percent:.1f}%\n"
                f"🧵 Потоков: {thread_count}\n"
                f"🆔 PID: {os.getpid()}\n"
            )

        except Exception as e:
            logger.error(f"Error getting bot status: {e}")
            message = (
                "*🤖 Состояние бота*\n\n"
                f"✅ Статус: Активен\n"
                f"❌ Не удалось получить детальную информацию\n"
                f"Ошибка: {str(e)}"
            )

        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data="bot_status"),
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_settings")
        )

        safe_send_message(self.bot, 
            chat_id,
            message,
            parse_mode='Markdown',
            reply_markup=markup
        )

    def _show_db_status(self, chat_id: int):
        """Show database status information"""
        db = self.db_manager.get_session()
        try:
            from src.models.models import Participant, Challenge, Event, Submission, EventRegistration

            # Count records
            participants_count = db.query(Participant).count()
            challenges_count = db.query(Challenge).count()
            events_count = db.query(Event).count()
            submissions_count = db.query(Submission).count()
            registrations_count = db.query(EventRegistration).count()

            # Active participants
            active_participants = db.query(Participant).filter(Participant.is_active == True).count()

            # Pending submissions
            from src.models.models import SubmissionStatus
            pending_submissions = db.query(Submission).filter(
                Submission.status == SubmissionStatus.PENDING
            ).count()

            message = (
                "*💾 База данных*\n\n"
                f"✅ Статус: Подключена\n\n"
                f"*Статистика:*\n"
                f"👥 Участников: {participants_count} (активных: {active_participants})\n"
                f"🏆 Челленджей: {challenges_count}\n"
                f"🎉 События: {events_count}\n"
                f"📝 Регистраций на события: {registrations_count}\n"
                f"📊 Отчетов: {submissions_count}\n"
                f"⏳ Ожидают модерации: {pending_submissions}\n"
            )

        except Exception as e:
            logger.error(f"Error getting database status: {e}")
            message = (
                "*💾 База данных*\n\n"
                f"❌ Ошибка подключения к базе данных\n"
                f"Ошибка: {str(e)}"
            )
        finally:
            db.close()

        markup = telebot.types.InlineKeyboardMarkup()
        markup.row(
            telebot.types.InlineKeyboardButton("🔄 Обновить", callback_data="db_status"),
            telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_settings")
        )

        safe_send_message(self.bot, 
            chat_id,
            message,
            parse_mode='Markdown',
            reply_markup=markup
        )



    def show_events_with_participants(self, chat_id: int):
        """Show list of events with participant counts"""
        db = self.db_manager.get_session()
        try:
            events = db.query(Event).filter(Event.is_active == True).order_by(Event.created_at.desc()).all()
            
            if not events:
                safe_send_message(self.bot, chat_id, "Нет активных событий")
                return
            
            message = "*📋 События с участниками:*\n\n"
            
            markup = telebot.types.InlineKeyboardMarkup()
            
            for event in events:
                # Count participants for this event
                participant_count = db.query(EventRegistration).filter(
                    EventRegistration.event_id == event.id,
                    EventRegistration.registration_status == SubmissionStatus.APPROVED
                ).count()
                
                # Format event type
                event_type_display = {
                    EventType.RUN_EVENT: "🏃 Забег",
                    EventType.CHALLENGE: "🏆 Челлендж", 
                    EventType.TOURNAMENT: "🏅 Турнир"
                }.get(event.event_type, event.event_type.value)
                
                message += f"🎯 *{event.name}* ({event_type_display})\n"
                message += f"👥 Участников: {participant_count}\n"
                message += f"📅 {event.start_date.strftime('%d.%m.%Y')}\n\n"
                
                # Add button to view participants
                button = telebot.types.InlineKeyboardButton(
                    f"👥 Участники ({participant_count})", 
                    callback_data=f"event_participants_{event.id}"
                )
                markup.row(button)
            
            markup.row(telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main"))
            
            safe_send_message(self.bot, 
                chat_id,
                message,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
        finally:
            db.close()
    
    def show_challenges_with_participants(self, chat_id: int):
        """Show list of challenges with participant counts"""
        db = self.db_manager.get_session()
        try:
            challenges = db.query(Challenge).filter(Challenge.is_active == True).order_by(Challenge.created_at.desc()).all()
            
            if not challenges:
                safe_send_message(self.bot, chat_id, "Нет активных челленджей")
                return
            
            message = "*📋 Челленджи с участниками:*\n\n"
            
            markup = telebot.types.InlineKeyboardMarkup()
            
            for challenge in challenges:
                # Count participants for this challenge
                participant_count = db.query(Submission).filter(
                    Submission.challenge_id == challenge.id,
                    Submission.status.in_([SubmissionStatus.APPROVED, SubmissionStatus.PENDING])
                ).count()
                
                # Format challenge type
                challenge_type_display = {
                    ChallengeType.PUSH_UPS: "💪 Отжимания",
                    ChallengeType.SQUATS: "🦵 Приседания",
                    ChallengeType.PLANK: "🧘 Планка",
                    ChallengeType.RUNNING: "🏃 Бег",
                    ChallengeType.STEPS: "🚶 Шаги"
                }.get(challenge.challenge_type, challenge.challenge_type.value)
                
                message += f"🏆 *{challenge.name}* ({challenge_type_display})\n"
                message += f"👥 Участников: {participant_count}\n"
                message += f"📅 {challenge.start_date.strftime('%d.%m.%Y')} - {challenge.end_date.strftime('%d.%m.%Y')}\n\n"
                
                # Add button to view participants
                button = telebot.types.InlineKeyboardButton(
                    f"👥 Участники ({participant_count})", 
                    callback_data=f"challenge_participants_{challenge.id}"
                )
                markup.row(button)
            
            markup.row(telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main"))
            
            safe_send_message(self.bot, 
                chat_id,
                message,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
        finally:
            db.close()
    
    def show_event_participants(self, chat_id: int, event_id: int):
        """Show participants for specific event"""
        db = self.db_manager.get_session()
        try:
            event = db.query(Event).filter(Event.id == event_id).first()
            if not event:
                safe_send_message(self.bot, chat_id, "Событие не найдено")
                return
            
            # Get participants for this event
            registrations = db.query(EventRegistration).filter(
                EventRegistration.event_id == event_id,
                EventRegistration.registration_status == SubmissionStatus.APPROVED
            ).join(Participant).order_by(Participant.full_name).all()
            
            message = f"*👥 Участники события: {event.name}*\n\n"
            
            if not registrations:
                message += "Пока нет зарегистрированных участников"
            else:
                message += f"Всего участников: {len(registrations)}\n\n"
                
                for i, reg in enumerate(registrations, 1):
                    participant = reg.participant
                    message += f"{i}. {participant.full_name}\n"
                    message += f"   📱 {participant.phone}\n"
                    message += f"   🎫 {participant.start_number}\n"
                    if reg.bib_number:
                        message += f"   🔢 Стартовый номер: {reg.bib_number}\n"
                    message += "\n"
            
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(telebot.types.InlineKeyboardButton("📋 Все события", callback_data="list_events"))
            markup.row(telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main"))
            
            safe_send_message(self.bot, 
                chat_id,
                message,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
        finally:
            db.close()
    
    def show_challenge_participants(self, chat_id: int, challenge_id: int):
        """Show participants for specific challenge"""
        db = self.db_manager.get_session()
        try:
            challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
            if not challenge:
                safe_send_message(self.bot, chat_id, "Челлендж не найден")
                return
            
            # Get participants for this challenge
            submissions = db.query(Submission).filter(
                Submission.challenge_id == challenge_id,
                Submission.status.in_([SubmissionStatus.APPROVED, SubmissionStatus.PENDING])
            ).join(Participant).order_by(Participant.full_name).all()
            
            message = f"*👥 Участники челленджа: {challenge.name}*\n\n"
            
            if not submissions:
                message += "Пока нет участников в этом челлендже"
            else:
                message += f"Всего участников: {len(submissions)}\n\n"
                
                # Group by participant to avoid duplicates
                unique_participants = {}
                for sub in submissions:
                    if sub.participant.id not in unique_participants:
                        unique_participants[sub.participant.id] = sub.participant
                
                for i, (pid, participant) in enumerate(unique_participants.items(), 1):
                    message += f"{i}. {participant.full_name}\n"
                    message += f"   📱 {participant.phone}\n"
                    message += f"   🎫 {participant.start_number}\n"
                    message += "\n"
            
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(telebot.types.InlineKeyboardButton("📋 Все челленджи", callback_data="list_challenges"))
            markup.row(telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="admin_main"))
            
            safe_send_message(self.bot, 
                chat_id,
                message,
                parse_mode='Markdown',
                reply_markup=markup
            )
            
        finally:
            db.close()