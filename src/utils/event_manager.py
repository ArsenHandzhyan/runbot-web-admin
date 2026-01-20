"""
Event Manager - Handles event creation, registration and management
"""

import telebot
from src.utils.telegram_retry import safe_send_message
import logging
from datetime import datetime
from typing import List, Optional
from sqlalchemy import func

from src.models.models import (
    Event, EventRegistration, EventSubmission, EventStatus, EventType,
    Participant, Challenge, Submission, SubmissionStatus,
    DistanceType, ChallengeType
)
from src.database.db import DatabaseManager

logger = logging.getLogger(__name__)

class EventManager:
    """Manages events, registrations and event submissions"""
    
    def __init__(self, bot: telebot.TeleBot, db_manager: DatabaseManager):
        self.bot = bot
        self.db_manager = db_manager
        self.temp_distance_selection = {}  # Temporary storage for distance selection during event registration
    
    def show_available_events(self, chat_id: int, event_type: Optional[EventType] = None):
        """Show list of available events"""
        logger.info(f"show_available_events called for chat_id {chat_id}, event_type {event_type}")
        db = self.db_manager.get_session()
        try:
            # Query events
            query = db.query(Event).filter(
                Event.status.in_([EventStatus.UPCOMING, EventStatus.ACTIVE]),
                Event.is_active == True
            )
            
            if event_type:
                query = query.filter(Event.event_type == event_type)
            
            events = query.order_by(Event.start_date).all()
            
            if not events:
                safe_send_message(self.bot, chat_id, "Нет доступных событий 😢")
                return
            
            # Create message
            message = "*🎉 Доступные события:*\n\n"
            
            for event in events:
                # Format dates
                start_date = event.start_date.strftime('%d.%m.%Y')
                end_date = event.end_date.strftime('%d.%m.%Y')
                
                # Event type display
                type_display = {
                    EventType.RUN_EVENT: "🏃 Забег",
                    EventType.CHALLENGE: "🏆 Челлендж",
                    EventType.TOURNAMENT: "🏅 Турнир"
                }.get(event.event_type, "❓ Неизвестно")
                
                # Status display
                status_display = {
                    EventStatus.UPCOMING: "📅 Скоро",
                    EventStatus.ACTIVE: "🟢 Активно"
                }.get(event.status, "❓")
                
                # Registration info
                registration_count = db.query(EventRegistration).filter(
                    EventRegistration.event_id == event.id
                ).count()
                
                max_participants_info = f" / {event.max_participants}" if event.max_participants else ""
                
                message += (
                    f"{status_display} *{event.name}*\n"
                    f"   {type_display}\n"
                    f"   📅 {start_date} - {end_date}\n"
                    f"   👥 Участников: {registration_count}{max_participants_info}\n"
                )
                
                if event.description:
                    message += f"   📝 {event.description[:100]}...\n"
                
                # Check if user is already registered
                participant = db.query(Participant).filter(
                    Participant.telegram_id == str(chat_id)
                ).first()
                
                markup = telebot.types.InlineKeyboardMarkup()
                
                if participant:
                    existing_registration = db.query(EventRegistration).filter(
                        EventRegistration.participant_id == participant.id,
                        EventRegistration.event_id == event.id
                    ).first()

                    if existing_registration:
                        message += f"   ✅ Вы зарегистрированы (номер: `{existing_registration.bib_number}`)\n"
                        markup.row(telebot.types.InlineKeyboardButton("📊 Моя статистика", callback_data=f"event_stats_{event.id}"))
                    else:
                        message += "   ➕ Можно зарегистрироваться\n"
                        markup.row(telebot.types.InlineKeyboardButton("📝 Зарегистрироваться", callback_data=f"event_register_{event.id}"))
                else:
                    message += "   ⚠️ Требуется регистрация в системе\n"
                    markup.row(telebot.types.InlineKeyboardButton("🏃 Зарегистрироваться", callback_data="register_now"))
                
                message += "\n"
                
                # Send message with buttons for each event
                safe_send_message(self.bot, 
                    chat_id, 
                    message, 
                    parse_mode='Markdown',
                    reply_markup=markup
                )
                # Reset message for next event
                message = ""
            
            # Add filter buttons at the end - always show them so user can switch filters
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("🏃 Забеги", callback_data="events_run"),
                telebot.types.InlineKeyboardButton("🏅 Турниры", callback_data="events_tournament")
            )
            markup.row(
                telebot.types.InlineKeyboardButton("📋 Все", callback_data="events_all")
            )

            safe_send_message(self.bot, 
                chat_id,
                "*Фильтры:*",
                parse_mode='Markdown',
                reply_markup=markup
            )
            
        except Exception as e:
            logger.error(f"Error showing events: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении списка событий")
        finally:
            db.close()
    
    def register_for_event(self, chat_id: int, event_id: int):
        """Register participant for an event"""
        db = self.db_manager.get_session()
        try:
            # Get participant
            participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id),
                Participant.is_active == True
            ).first()
            
            if not participant:
                safe_send_message(self.bot, 
                    chat_id,
                    "Для регистрации на события необходимо зарегистрироваться в RunBot!\n"
                    "Используйте команду /register"
                )
                return False
            
            # Get event
            event = db.query(Event).get(event_id)
            if not event:
                safe_send_message(self.bot, chat_id, "Событие не найдено")
                return False
            
            # Check if already registered
            existing_registration = db.query(EventRegistration).filter(
                EventRegistration.participant_id == participant.id,
                EventRegistration.event_id == event_id
            ).first()
            
            if existing_registration:
                safe_send_message(self.bot, chat_id, "Вы уже зарегистрированы на это событие!")
                return False
            
            # Check if participant has distance type for run events
            if event.event_type == EventType.RUN_EVENT and not participant.distance_type:
                # Need to ask for distance type
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
                markup.row('🏃 Взрослый забег', '👶 Детский забег')

                safe_send_message(self.bot, 
                    chat_id,
                    "⚠️ Для участия в забеге необходимо выбрать дистанцию:\n\n"
                    "Выберите подходящую категорию:",
                    reply_markup=markup
                )

                # Store event_id in temporary session for later processing
                # Use string for chat_id to match how it's used in bot.py
                self.temp_distance_selection[str(chat_id)] = {
                    'event_id': event_id,
                    'action': 'event_registration'
                }
                # Return True to prevent showing events list
                return True
            
            # Check registration deadline
            if event.registration_deadline and datetime.now() > event.registration_deadline:
                safe_send_message(self.bot, chat_id, "Регистрация на это событие уже закрыта")
                return
            
            # Check participant limit
            if event.max_participants:
                current_registrations = db.query(EventRegistration).filter(
                    EventRegistration.event_id == event_id
                ).count()
                
                if current_registrations >= event.max_participants:
                    safe_send_message(self.bot, chat_id, "Достигнут лимит участников для этого события")
                    return
            
            # Generate bib number
            bib_prefix = {
                EventType.RUN_EVENT: "RUN",
                EventType.CHALLENGE: "CH",
                EventType.TOURNAMENT: "TRN"
            }.get(event.event_type, "EVT")
            
            # Get next bib number
            last_registration = db.query(EventRegistration).filter(
                EventRegistration.event_id == event_id
            ).order_by(EventRegistration.id.desc()).first()

            if last_registration and last_registration.bib_number:
                try:
                    # Extract numeric part from bib_number (handle any prefix format)
                    import re
                    # Match all digits in the bib number
                    match = re.search(r'(\d+)$', last_registration.bib_number)
                    if match:
                        last_number = int(match.group(1))
                        bib_number = f"{bib_prefix}{last_number + 1:03d}"
                    else:
                        # If no number found, start from 001
                        bib_number = f"{bib_prefix}001"
                except (ValueError, AttributeError) as e:
                    # If parsing fails, start from 001
                    logger.warning(f"Failed to parse bib number '{last_registration.bib_number}': {e}, starting from 001")
                    bib_number = f"{bib_prefix}001"
            else:
                bib_number = f"{bib_prefix}001"
            
            # Create registration
            registration = EventRegistration(
                participant_id=participant.id,
                event_id=event_id,
                bib_number=bib_number,
                registration_status=SubmissionStatus.APPROVED
            )
            
            db.add(registration)
            db.commit()
            
            # Success message
            event_type_display = {
                EventType.RUN_EVENT: "забег",
                EventType.CHALLENGE: "челлендж",
                EventType.TOURNAMENT: "турнир"
            }.get(event.event_type, "событие")
            
            success_message = (
                f"✅ *Регистрация успешна!*\n\n"
                f"Вы зарегистрированы на {event_type_display}:\n"
                f"🎯 *{event.name}*\n\n"
                f"Ваш стартовый номер: `{bib_number}`\n"
                f"Не забудьте принять участие!"
            )
            
            safe_send_message(self.bot, chat_id, success_message, parse_mode='Markdown')
            logger.info(f"Participant {participant.id} registered for event {event_id}")

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error registering for event: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при регистрации на событие")
            return False
        finally:
            db.close()
    
    def show_my_events(self, chat_id: int):
        """Show events where participant is registered"""
        db = self.db_manager.get_session()
        try:
            # Get participant
            participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id)
            ).first()
            
            if not participant:
                safe_send_message(self.bot, 
                    chat_id,
                    "Для просмотра ваших событий необходимо зарегистрироваться в RunBot!\n"
                    "Используйте команду /register"
                )
                return
            
            # Get registrations with event info
            registrations = db.query(EventRegistration, Event).join(Event).filter(
                EventRegistration.participant_id == participant.id
            ).order_by(Event.start_date.desc()).all()
            
            if not registrations:
                safe_send_message(self.bot, chat_id, "Вы пока не зарегистрированы ни на одно событие")
                return
            
            # Create message
            message = "*📋 Мои события:*\n\n"
            
            for registration, event in registrations:
                # Event type display
                type_display = {
                    EventType.RUN_EVENT: "🏃 Забег",
                    EventType.CHALLENGE: "🏆 Челлендж",
                    EventType.TOURNAMENT: "🏅 Турнир"
                }.get(event.event_type, "❓")
                
                # Status display
                status_display = {
                    EventStatus.UPCOMING: "📅 Предстоит",
                    EventStatus.ACTIVE: "🟢 Активно",
                    EventStatus.FINISHED: "🏁 Завершено",
                    EventStatus.CANCELLED: "❌ Отменено"
                }.get(event.status, "❓")
                
                message += (
                    f"{status_display} *{event.name}*\n"
                    f"   {type_display}\n"
                    f"   🏷️ Номер: {registration.bib_number}\n"
                    f"   📅 {event.start_date.strftime('%d.%m.%Y')} - {event.end_date.strftime('%d.%m.%Y')}\n\n"
                )
            
            safe_send_message(self.bot, chat_id, message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing participant events: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении списка ваших событий")
        finally:
            db.close()
    
    def create_event(self, name: str, event_type: EventType, start_date: datetime,
                    end_date: datetime, description: str = "",
                    distance_type: Optional[DistanceType] = None,
                    challenge_type: Optional[ChallengeType] = None,
                    max_participants: Optional[int] = None) -> bool:
        """Create a new event (admin function)"""
        db = self.db_manager.get_session()
        try:
            event = Event(
                name=name,
                event_type=event_type,
                start_date=start_date,
                end_date=end_date,
                description=description,
                distance_type=distance_type,
                challenge_type=challenge_type,
                max_participants=max_participants,
                status=EventStatus.UPCOMING,
                is_active=True
            )

            db.add(event)
            db.commit()
            db.refresh(event)  # Refresh to ensure data is persisted

            logger.info(f"New event created: {name} ({event_type.value}) with ID {event.id}")
            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating event: {e}")
            logger.error(f"Event data: name={name}, type={event_type}, start={start_date}, end={end_date}")
            return False
        finally:
            db.close()
    
    def get_event_statistics(self, event_id: int) -> dict:
        """Get statistics for a specific event"""
        db = self.db_manager.get_session()
        try:
            event = db.query(Event).get(event_id)
            if not event:
                return {}
            
            # Get registration count
            total_registrations = db.query(EventRegistration).filter(
                EventRegistration.event_id == event_id
            ).count()
            
            # Get submission statistics
            submissions_query = db.query(EventSubmission).join(EventRegistration).filter(
                EventRegistration.event_id == event_id
            )
            
            total_submissions = submissions_query.count()
            approved_submissions = submissions_query.filter(
                EventSubmission.status == SubmissionStatus.APPROVED
            ).count()
            pending_submissions = submissions_query.filter(
                EventSubmission.status == SubmissionStatus.PENDING
            ).count()
            
            # Calculate approval rate
            approval_rate = (approved_submissions / total_submissions * 100) if total_submissions > 0 else 0
            
            return {
                'event_name': event.name,
                'event_type': event.event_type.value,
                'total_registrations': total_registrations,
                'total_submissions': total_submissions,
                'approved_submissions': approved_submissions,
                'pending_submissions': pending_submissions,
                'approval_rate': round(approval_rate, 1)
            }
            
        except Exception as e:
            logger.error(f"Error getting event statistics: {e}")
            return {}
        finally:
            db.close()

    def show_event_participants(self, chat_id: int, event_id: int):
        """Show list of participants registered for specific event (for admin panel)"""
        db = self.db_manager.get_session()
        try:
            # Get event
            event = db.query(Event).get(event_id)
            if not event:
                safe_send_message(self.bot, chat_id, "Событие не найдено")
                return

            # Get participants registered for this event
            registrations = db.query(EventRegistration, Participant).join(Participant).filter(
                EventRegistration.event_id == event_id
            ).order_by(EventRegistration.registration_date.desc()).all()

            if not registrations:
                safe_send_message(self.bot, chat_id, f"На событие *{event.name}* пока никто не зарегистрировался", parse_mode='Markdown')
                return

            # Create message
            message = f"*👥 Участники события: {event.name}*\n\n"
            
            for i, (registration, participant) in enumerate(registrations, 1):
                # Get participant's distance type if applicable
                distance_info = ""
                if participant.distance_type:
                    distance_name = "Взрослый забег" if participant.distance_type == DistanceType.ADULT_RUN else "Детский забег"
                    distance_info = f" | {distance_name}"
                
                message += (
                    f"{i}. `{participant.start_number}` - {participant.full_name}\n"
                    f"   📞 {participant.phone} | 📅 {registration.registration_date.strftime('%d.%m.%Y')}\n"
                    f"   🏷️ Номер в событии: {registration.bib_number}{distance_info}\n\n"
                )
            
            message += f"📊 Всего участников: {len(registrations)}"

            # Add navigation button
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="participants_menu")
            )

            safe_send_message(self.bot, chat_id, message, parse_mode='Markdown', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error showing event participants: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении списка участников")
        finally:
            db.close()

    def handle_callback_query(self, call):
        """Handle callback queries for events"""
        try:
            callback_data = call.data
            logger.info(f"Event manager handling callback: {callback_data} from {call.from_user.id}")

            # Handle event type filters
            if callback_data == 'events_all':
                self.bot.answer_callback_query(call.id, "Показываю все события")
                self.show_available_events(call.message.chat.id, event_type=None)
            elif callback_data == 'events_run':
                self.bot.answer_callback_query(call.id, "Показываю забеги")
                self.show_available_events(call.message.chat.id, event_type=EventType.RUN_EVENT)
            elif callback_data == 'events_tournament':
                self.bot.answer_callback_query(call.id, "Показываю турниры")
                self.show_available_events(call.message.chat.id, event_type=EventType.TOURNAMENT)
            elif callback_data == 'events_challenge':
                self.bot.answer_callback_query(call.id, "Показываю челленджи-события")
                self.show_available_events(call.message.chat.id, event_type=EventType.CHALLENGE)
            # Handle event registration
            elif callback_data.startswith('event_register_'):
                event_id = int(callback_data.split('_')[2])
                self.bot.answer_callback_query(call.id)
                registration_success = self.register_for_event(call.message.chat.id, event_id)

                # Auto-refresh events list after registration (if not redirected to distance selection)
                if registration_success and str(call.message.chat.id) not in self.temp_distance_selection:
                    logger.info(f"Refreshing events list after registration for user {call.message.chat.id}")
                    self.show_available_events(call.message.chat.id)
            # Handle event stats
            elif callback_data.startswith('event_stats_'):
                event_id = int(callback_data.split('_')[2])
                self.bot.answer_callback_query(call.id, "Получаю статистику...")
                stats = self.get_event_statistics(event_id)
                if stats:
                    message = f"📊 Статистика события *{stats['event_name']}*:\n\n"
                    message += f"👥 Зарегистрировано: {stats['total_registrations']}\n"
                    message += f"📝 Отчётов: {stats['total_submissions']}\n"
                    message += f"✅ Одобрено: {stats['approved_submissions']}\n"
                    message += f"⏳ Ожидают: {stats['pending_submissions']}\n"
                    safe_send_message(self.bot, call.message.chat.id, message, parse_mode='Markdown')
                else:
                    safe_send_message(self.bot, call.message.chat.id, "Не удалось получить статистику")
            # Handle event participants (for admin panel)
            elif callback_data.startswith('event_participants_'):
                event_id = int(callback_data.split('_')[2])
                self.bot.answer_callback_query(call.id, "Получаю список участников...")
                self.show_event_participants(call.message.chat.id, event_id)
            else:
                self.bot.answer_callback_query(call.id, "Неизвестная команда")

        except Exception as e:
            logger.error(f"Error handling event callback: {e}")
            import traceback
            traceback.print_exc()
            self.bot.answer_callback_query(call.id, "Ошибка обработки запроса")