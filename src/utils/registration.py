"""
Registration Manager
Handles participant registration workflow
"""

import telebot
from src.utils.telegram_retry import safe_send_message
import re
from datetime import datetime, date
from typing import Dict, Optional
import logging

from src.models.models import Participant, DistanceType
from src.database.db import DatabaseManager

logger = logging.getLogger(__name__)

class RegistrationManager:
    """Manages participant registration process"""

    def __init__(self, bot: telebot.TeleBot, db_manager: DatabaseManager, admin_notification_callback=None):
        self.bot = bot
        self.db_manager = db_manager
        self.active_registrations: Dict[int, dict] = {}  # chat_id -> registration_data
        self.admin_notification_callback = admin_notification_callback  # Callback to notify admins
    
    def start_registration(self, chat_id: int):
        """Start registration process for a user"""
        # Check if user is already registered
        db = self.db_manager.get_session()
        try:
            existing_participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id)
            ).first()
            
            if existing_participant:
                safe_send_message(self.bot, 
                    chat_id, 
                    f"Вы уже зарегистрированы в RunBot!\n"
                    f"Регистрационный номер: {existing_participant.start_number}" + 
                    (f"\nДистанция: {'Взрослая' if existing_participant.distance_type == DistanceType.ADULT_RUN else 'Детская'}" 
                     if existing_participant.distance_type else "")
                )
                return
        finally:
            db.close()
        
        # Start new registration
        self.active_registrations[chat_id] = {
            'step': 'full_name',
            'data': {}
        }
        
        safe_send_message(self.bot, 
            chat_id,
            "📝 *Регистрация в RunBot*\n\n"
            "Пожалуйста, введите ваше ФИО полностью:",
            parse_mode='Markdown'
        )
    
    def handle_text_input(self, message):
        """Handle text input during registration process"""
        chat_id = message.chat.id
        text = message.text.strip()
        
        if chat_id not in self.active_registrations:
            return
        
        registration_data = self.active_registrations[chat_id]
        step = registration_data['step']
        
        try:
            if step == 'full_name':
                self._handle_full_name(chat_id, text)
            elif step == 'birth_date':
                self._handle_birth_date(chat_id, text)
            elif step == 'phone':
                self._handle_phone(chat_id, text)
            elif step == 'confirm_basic':
                self._handle_basic_confirmation(chat_id, text)
        except Exception as e:
            logger.error(f"Registration error: {e}")
            safe_send_message(self.bot, chat_id, "Произошла ошибка. Попробуйте снова.")
            del self.active_registrations[chat_id]
    
    def _handle_full_name(self, chat_id: int, full_name: str):
        """Handle full name input"""
        if len(full_name) < 5:
            safe_send_message(self.bot, chat_id, "Пожалуйста, введите полное ФИО (минимум 5 символов)")
            return
            
        self.active_registrations[chat_id]['data']['full_name'] = full_name
        self.active_registrations[chat_id]['step'] = 'birth_date'
        
        safe_send_message(self.bot, 
            chat_id,
            "Введите дату рождения в формате ДД.ММ.ГГГГ (например: 15.03.1990):"
        )
    
    def _handle_birth_date(self, chat_id: int, birth_date_str: str):
        """Handle birth date input"""
        try:
            # Parse date
            birth_date = datetime.strptime(birth_date_str, "%d.%m.%Y").date()
            
            # Check if date is valid (not in future, reasonable age)
            today = date.today()
            if birth_date > today:
                safe_send_message(self.bot, chat_id, "Дата рождения не может быть в будущем!")
                return
                
            age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
            if age < 5 or age > 100:
                safe_send_message(self.bot, chat_id, "Пожалуйста, введите корректную дату рождения")
                return
            
            self.active_registrations[chat_id]['data']['birth_date'] = birth_date
            self.active_registrations[chat_id]['step'] = 'phone'
            
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            contact_button = telebot.types.KeyboardButton("📱 Поделиться контактом", request_contact=True)
            markup.add(contact_button)
            
            safe_send_message(self.bot, 
                chat_id,
                "Введите номер телефона для связи:",
                reply_markup=markup
            )
            
        except ValueError:
            safe_send_message(self.bot, chat_id, "Неверный формат даты. Используйте ДД.ММ.ГГГГ")
    
    def _handle_phone(self, chat_id: int, phone: str):
        """Handle phone input"""
        # If it's a contact sharing
        if hasattr(phone, 'contact') and phone.contact:
            phone_number = phone.contact.phone_number
        else:
            # Clean phone number
            phone_number = re.sub(r'[^\d+]', '', phone)
            
            # Validate phone number
            if not re.match(r'^(\+7|8|\+?\d{1,3})\d{10}$', phone_number):
                safe_send_message(self.bot, 
                    chat_id, 
                "Неверный формат телефона. Пожалуйста, введите номер в формате +7XXXXXXXXXX или 8XXXXXXXXXX"
                )
                return
        
        self.active_registrations[chat_id]['data']['phone'] = phone_number
        self.active_registrations[chat_id]['step'] = 'confirm_basic'
        
        # Show basic confirmation without distance
        reg_data = self.active_registrations[chat_id]['data']
        confirmation_text = (
            f"Проверьте введенные данные:\n\n"
            f"📋 ФИО: {reg_data['full_name']}\n"
            f"🎂 Дата рождения: {reg_data['birth_date'].strftime('%d.%m.%Y')}\n"
            f"📞 Телефон: {reg_data['phone']}\n\n"
            f"Все верно? Ответьте 'Да' для подтверждения или 'Нет' для повтора."
        )
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row('✅ Да', '❌ Нет')
        
        safe_send_message(self.bot, chat_id, confirmation_text, reply_markup=markup)
    
    def _handle_distance_selection(self, chat_id: int, text: str):
        """Handle distance selection"""
        if 'взрослый' in text.lower():
            distance_type = DistanceType.ADULT_RUN
        elif 'детский' in text.lower():
            distance_type = DistanceType.CHILDREN_RUN
        else:
            safe_send_message(self.bot, chat_id, "Пожалуйста, выберите одну из опций")
            return
        
        self.active_registrations[chat_id]['data']['distance_type'] = distance_type
        self.active_registrations[chat_id]['step'] = 'confirm'
        
        # Show confirmation
        reg_data = self.active_registrations[chat_id]['data']
        confirmation_text = (
            f"Проверьте введенные данные:\n\n"
            f"📋 ФИО: {reg_data['full_name']}\n"
            f"🎂 Дата рождения: {reg_data['birth_date'].strftime('%d.%m.%Y')}\n"
            f"📞 Телефон: {reg_data['phone']}\n"
            f"🏁 Дистанция: {'Взрослый забег' if distance_type == DistanceType.ADULT_RUN else 'Детский забег'}\n\n"
            f"Все верно? Ответьте 'Да' для подтверждения или 'Нет' для повтора."
        )
        
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row('✅ Да', '❌ Нет')
        
        safe_send_message(self.bot, chat_id, confirmation_text, reply_markup=markup)
    
    def _handle_basic_confirmation(self, chat_id: int, text: str):
        """Handle basic confirmation without distance"""
        if 'да' in text.lower():
            self._complete_basic_registration(chat_id)
        elif 'нет' in text.lower():
            # Restart registration
            del self.active_registrations[chat_id]
            self.start_registration(chat_id)
        else:
            safe_send_message(self.bot, chat_id, "Пожалуйста, ответьте 'Да' или 'Нет'")
    
    def _complete_basic_registration(self, chat_id: int):
        """Complete the basic registration process without distance"""
        reg_data = self.active_registrations[chat_id]['data']
        
        db = self.db_manager.get_session()
        try:
            # Generate unique start number (without distance type)
            start_number = self._generate_basic_start_number(db)
            
            # Create participant without distance type
            participant = Participant(
                telegram_id=str(chat_id),
                full_name=reg_data['full_name'],
                birth_date=reg_data['birth_date'],
                phone=reg_data['phone'],
                start_number=start_number,
                distance_type=None  # Will be set later when participating in events
            )
            
            db.add(participant)
            db.commit()
            
            # Send success message
            success_text = (
                f"🎉 *Регистрация в RunBot успешно завершена!*\n\n"
                f"Ваш регистрационный номер: `{start_number}`\n\n"
                f"Теперь вы можете:\n"
                f"• Посмотреть доступные события: /events\n"
                f"• Посмотреть доступные челленджи: /challenges\n"
                f"• Отправить отчет: /submit\n"
                f"• Посмотреть статистику: /stats\n\n"
                f"Для участия в конкретных забегах или челленджах\n"
                f"вам потребуется указать дополнительные данные."
            )
            
            # Create full navigation menu
            def create_full_navigation_keyboard():
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
                markup.row('🏃 Регистрация', '🎉 События')
                markup.row('🏆 Челленджи', '📊 Статистика')
                markup.row('ℹ️ Помощь', '🏠 Главное меню')
                return markup
            
            markup = create_full_navigation_keyboard()
            safe_send_message(self.bot, chat_id, success_text, parse_mode='Markdown', reply_markup=markup)
            
            logger.info(f"New participant registered: {reg_data['full_name']} with number {start_number}")

            # Notify admins about new registration
            self._notify_admins_about_new_participant(participant)

        except Exception as e:
            db.rollback()
            logger.error(f"Basic registration database error: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при регистрации. Попробуйте позже.")
        finally:
            db.close()
            # Clean up registration data
            if chat_id in self.active_registrations:
                del self.active_registrations[chat_id]
    
    def _complete_registration(self, chat_id: int, distance_type: DistanceType = None):
        """Complete the registration process with optional distance (for events)"""
        reg_data = self.active_registrations[chat_id]['data']
        
        db = self.db_manager.get_session()
        try:
            # Get existing participant
            participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id)
            ).first()
            
            if participant:
                # Update distance if provided
                if distance_type:
                    participant.distance_type = distance_type
                    start_number = participant.start_number
                else:
                    start_number = participant.start_number
            else:
                # Generate unique start number
                start_number = self._generate_start_number(db, distance_type) if distance_type else self._generate_basic_start_number(db)
                
                # Create participant
                participant = Participant(
                    telegram_id=str(chat_id),
                    full_name=reg_data['full_name'],
                    birth_date=reg_data['birth_date'],
                    phone=reg_data['phone'],
                    distance_type=distance_type,
                    start_number=start_number
                )
                db.add(participant)
            
            db.commit()
            
            # Send success message
            success_text = (
                f"🎉 *Регистрация в RunBot успешно завершена!*\n\n"
                f"Ваш регистрационный номер: `{start_number}`\n"
                f"Дистанция: {'Взрослый забег' if distance_type == DistanceType.ADULT_RUN else 'Детский забег' if distance_type == DistanceType.CHILDREN_RUN else 'Не указана'}\n\n"
                f"Теперь вы можете:\n"
                f"• Посмотреть доступные челленджи: /challenges\n"
                f"• Отправить отчет: /submit\n"
                f"• Посмотреть статистику: /stats"
            )
            
            # Create full navigation menu
            def create_full_navigation_keyboard():
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
                markup.row('🏃 Регистрация', '🎉 События')
                markup.row('🏆 Челленджи', '📊 Статистика')
                markup.row('ℹ️ Помощь', '🏠 Главное меню')
                return markup
            
            markup = create_full_navigation_keyboard()
            safe_send_message(self.bot, chat_id, success_text, parse_mode='Markdown', reply_markup=markup)
            
            logger.info(f"Participant updated: {reg_data['full_name']} with number {start_number}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Registration database error: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при регистрации. Попробуйте позже.")
        finally:
            db.close()
            # Clean up registration data
            if chat_id in self.active_registrations:
                del self.active_registrations[chat_id]
    
    def _generate_basic_start_number(self, db) -> str:
        """Generate unique start number for basic registration"""
        # Count all existing participants
        count = db.query(Participant).filter(Participant.is_active == True).count()
        number = str(count + 1).zfill(3)
        return f"REG{number}"
    
    def _generate_start_number(self, db, distance_type: DistanceType) -> str:
        """Generate unique start number"""
        # Count existing participants for this distance
        count = db.query(Participant).filter(
            Participant.distance_type == distance_type,
            Participant.is_active == True
        ).count()

        # Generate number based on distance type
        prefix = "A" if distance_type == DistanceType.ADULT_RUN else "C"
        number = str(count + 1).zfill(3)

        return f"{prefix}{number}"

    def _notify_admins_about_new_participant(self, participant: Participant):
        """Notify all admins about new participant registration"""
        if self.admin_notification_callback:
            try:
                # Call the callback with participant info
                self.admin_notification_callback(participant)
            except Exception as e:
                logger.error(f"Error notifying admins about new participant: {e}")

    def handle_callback_query(self, call):
        """Handle callback queries for registration"""
        try:
            callback_data = call.data
            logger.info(f"Registration manager handling callback: {callback_data} from {call.from_user.id}")

            if callback_data == 'register_now':
                self.bot.answer_callback_query(call.id, "Начинаем регистрацию...")
                self.start_registration(call.message.chat.id)
            else:
                self.bot.answer_callback_query(call.id, "Неизвестная команда")

        except Exception as e:
            logger.error(f"Error handling registration callback: {e}")
            import traceback
            traceback.print_exc()
            self.bot.answer_callback_query(call.id, "Ошибка обработки запроса")