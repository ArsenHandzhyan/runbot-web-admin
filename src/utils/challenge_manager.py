"""
Challenge Manager
Handles challenge listings, submissions, and participant interactions
"""

import telebot
from src.utils.telegram_retry import safe_send_message
import os
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import logging

from src.models.models import Participant, Challenge, Submission, ChallengeType, SubmissionStatus, ChallengeRegistration, DistanceType
from src.database.db import DatabaseManager
from src.utils.storage import get_storage_manager
from sqlalchemy import func

logger = logging.getLogger(__name__)

class ChallengeManager:
    """Manages challenges and submissions"""
    
    def __init__(self, bot: telebot.TeleBot, db_manager: DatabaseManager):
        self.bot = bot
        self.db_manager = db_manager
        self.active_submissions: Dict[int, dict] = {}  # chat_id -> submission_data
        self.temp_challenge_selection = {}  # Temporary storage for challenge selection during participation
    
    def register_for_challenge(self, chat_id: int, challenge_id: int):
        """Register participant for a challenge with simple confirmation"""
        db = self.db_manager.get_session()
        try:
            # Check if participant is registered
            participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id),
                Participant.is_active == True
            ).first()
            
            if not participant:
                safe_send_message(self.bot, 
                    chat_id, 
                    "Для участия в челлендже необходимо зарегистрироваться в RunBot!\n"
                    "Используйте команду /register"
                )
                return False
            
            # Get the challenge
            challenge = db.query(Challenge).filter(
                Challenge.id == challenge_id,
                Challenge.is_active == True,
                Challenge.end_date >= datetime.now()
            ).first()
            
            if not challenge:
                safe_send_message(self.bot, chat_id, "Челлендж не найден или завершен")
                return False
            
            # Check if already registered
            existing_registration = db.query(ChallengeRegistration).filter(
                ChallengeRegistration.participant_id == participant.id,
                ChallengeRegistration.challenge_id == challenge_id,
                ChallengeRegistration.is_active == True
            ).first()
            
            if existing_registration:
                safe_send_message(self.bot, 
                    chat_id, 
                    f"✅ Вы уже зарегистрированы на челлендж:\n\n"
                    f"🎯 *{challenge.name}*\n\n"
                    f"Ваш номер: `{existing_registration.bib_number}`\n"
                    f"📊 Для отправки отчета используйте команду /submit"
                )
                return True
            
            # Generate bib number
            bib_prefix = "CH"
            
            # Get next bib number
            last_registration = db.query(ChallengeRegistration).filter(
                ChallengeRegistration.challenge_id == challenge_id
            ).order_by(ChallengeRegistration.id.desc()).first()
            
            if last_registration and last_registration.bib_number:
                last_number = int(last_registration.bib_number.replace(bib_prefix, ""))
                bib_number = f"{bib_prefix}{last_number + 1:03d}"
            else:
                bib_number = f"{bib_prefix}001"
            
            # Create registration
            registration = ChallengeRegistration(
                participant_id=participant.id,
                challenge_id=challenge_id,
                bib_number=bib_number
            )
            
            db.add(registration)
            db.commit()
            
            # Success message
            success_message = (
                f"✅ *Регистрация успешна!*\n\n"
                f"Вы зарегистрированы на челлендж:\n"
                f"🎯 *{challenge.name}*\n\n"
                f"Ваш стартовый номер: `{bib_number}`\n"
                f"Не забудьте принять участие!\n\n"
                f"📊 Для отправки отчета используйте команду /submit"
            )
            
            safe_send_message(self.bot, chat_id, success_message, parse_mode='Markdown')
            logger.info(f"Participant {participant.id} registered for challenge {challenge_id}")

            return True

        except Exception as e:
            db.rollback()
            logger.error(f"Error registering for challenge: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при регистрации на челлендж")
            return False
        finally:
            db.close()
            # Refresh the challenges list to show updated status after db is closed
            try:
                self.show_active_challenges(chat_id)
            except Exception as e:
                logger.error(f"Error refreshing challenges list: {e}")
    
    def show_active_challenges(self, chat_id: int, challenge_type=None):
        """Show list of active challenges with optional filtering by type"""
        db = self.db_manager.get_session()
        try:
            # Get active challenges
            query = db.query(Challenge).filter(
                Challenge.is_active == True,
                Challenge.end_date >= datetime.now()
            )

            # Apply filter if specified
            if challenge_type:
                query = query.filter(Challenge.challenge_type == challenge_type)

            challenges = query.all()
            
            if not challenges:
                safe_send_message(self.bot, chat_id, "Активных челленджей нет 😢")
                return
            
            # Create challenge list message
            for challenge in challenges:
                days_left = (challenge.end_date - datetime.now()).days
                message = (
                    f"🏆 *{challenge.name}*\n"
                    f"{challenge.description}\n"
                    f"📅 До окончания: {days_left} дней\n"
                    f"🔢 Тип: {self._get_challenge_type_display(challenge.challenge_type)}\n\n"
                )
                
                # Check if user is registered
                participant = db.query(Participant).filter(
                    Participant.telegram_id == str(chat_id),
                    Participant.is_active == True
                ).first()
                
                markup = telebot.types.InlineKeyboardMarkup()
                
                if participant:
                    # Check if user is already registered for this challenge
                    existing_registration = db.query(ChallengeRegistration).filter(
                        ChallengeRegistration.participant_id == participant.id,
                        ChallengeRegistration.challenge_id == challenge.id,
                        ChallengeRegistration.is_active == True
                    ).first()
                    
                    if existing_registration:
                        # User is registered - check for recent submissions
                        recent_submission = db.query(Submission).filter(
                            Submission.participant_id == participant.id,
                            Submission.challenge_id == challenge.id,
                            Submission.submission_date >= datetime.now() - timedelta(days=1)  # Submitted today
                        ).first()

                        if recent_submission:
                            markup.row(telebot.types.InlineKeyboardButton("✅ Уже участвуете", callback_data="challenge_already_submitted"))
                            message += f"✅ Вы зарегистрированы (номер: `{existing_registration.bib_number}`)\n"
                            message += "✅ Отчет за сегодня уже отправлен\n\n"
                        else:
                            markup.row(telebot.types.InlineKeyboardButton("📊 Отправить отчет", callback_data=f"submit_challenge_{challenge.id}"))
                            message += f"✅ Вы зарегистрированы (номер: `{existing_registration.bib_number}`)\n"
                            message += "📊 Отправьте отчет о выполнении!\n\n"
                    else:
                        # Check if challenge requires distance selection
                        if challenge.challenge_type in [ChallengeType.RUNNING] and not participant.distance_type:
                            # Need to ask for distance type first
                            markup.row(telebot.types.InlineKeyboardButton("🏃 Участвовать", callback_data=f"challenge_join_dist_{challenge.id}"))
                            message += "➕ Нажмите \"Участвовать\", чтобы выбрать дистанцию\n\n"
                        else:
                            markup.row(telebot.types.InlineKeyboardButton("🏃 Участвовать", callback_data=f"challenge_join_{challenge.id}"))
                            message += "➕ Нажмите \"Участвовать\", чтобы начать участие\n\n"
                else:
                    markup.row(telebot.types.InlineKeyboardButton("🏃 Зарегистрироваться", callback_data="register_now"))
                    message += "⚠️ Требуется регистрация для участия\n\n"
                
                safe_send_message(self.bot, chat_id, message, parse_mode='Markdown', reply_markup=markup)

            # Add filter buttons at the end - always show them so user can switch filters
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("💪 Отжимания", callback_data="challenges_push_ups"),
                telebot.types.InlineKeyboardButton("🦵 Приседания", callback_data="challenges_squats")
            )
            markup.row(
                telebot.types.InlineKeyboardButton("🏃 Бег", callback_data="challenges_running"),
                telebot.types.InlineKeyboardButton("👣 Шаги", callback_data="challenges_steps")
            )
            markup.row(
                telebot.types.InlineKeyboardButton("🧘 Планка", callback_data="challenges_plank"),
                telebot.types.InlineKeyboardButton("📋 Все", callback_data="challenges_all")
            )

            safe_send_message(self.bot, 
                chat_id,
                "*Фильтры:*",
                parse_mode='Markdown',
                reply_markup=markup
            )

            # Add general submit button at the end
            safe_send_message(self.bot, chat_id, "Хотите отправить отчет? Используйте команду /submit")
            
        except Exception as e:
            logger.error(f"Error showing challenges: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении списка челленджей")
        finally:
            db.close()
    
    def start_submission_process(self, chat_id: int):
        """Start submission process for a participant"""
        # Check if participant is registered
        db = self.db_manager.get_session()
        try:
            participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id),
                Participant.is_active == True
            ).first()
            
            if not participant:
                safe_send_message(self.bot, 
                    chat_id, 
                    "Для отправки отчетов необходимо зарегистрироваться в RunBot!\n"
                    "Используйте команду /register"
                )
                return
            
            # Get active challenges
            challenges = db.query(Challenge).filter(
                Challenge.is_active == True,
                Challenge.end_date >= datetime.now()
            ).all()
            
            if not challenges:
                safe_send_message(self.bot, chat_id, "Нет активных челленджей для отправки отчетов")
                return
            
            # Start submission process
            self.active_submissions[chat_id] = {
                'step': 'select_challenge',
                'participant_id': participant.id,
                'data': {}
            }
            
            # Create challenge selection menu
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
            for challenge in challenges:
                button_text = f"{self._get_challenge_type_display(challenge.challenge_type)} - {challenge.name}"
                markup.add(button_text)
            
            safe_send_message(self.bot, 
                chat_id,
                "Выберите челлендж для отправки отчета:",
                reply_markup=markup
            )
            
        except Exception as e:
            logger.error(f"Error starting submission: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при начале процесса отправки")
        finally:
            db.close()
    
    def handle_text_input(self, message):
        """Handle text input during submission process"""
        chat_id = message.chat.id
        text = message.text.strip()
        
        if chat_id not in self.active_submissions:
            return
        
        submission_data = self.active_submissions[chat_id]
        step = submission_data['step']
        
        try:
            if step == 'select_challenge':
                self._handle_challenge_selection(chat_id, text)
            elif step == 'enter_result':
                self._handle_result_input(chat_id, text)
            elif step == 'enter_comment':
                self._handle_comment_input(chat_id, text)
        except Exception as e:
            logger.error(f"Submission error: {e}")
            safe_send_message(self.bot, chat_id, "Произошла ошибка. Попробуйте снова.")
            del self.active_submissions[chat_id]
    
    def handle_media_upload(self, message):
        """Handle media upload during submission process"""
        chat_id = message.chat.id
        
        if chat_id not in self.active_submissions:
            return
        
        submission_data = self.active_submissions[chat_id]
        step = submission_data['step']
        
        if step != 'upload_media':
            return
        
        try:
            # Save media file
            media_path = self._save_media(message)
            if not media_path:
                safe_send_message(self.bot, chat_id, "Ошибка при сохранении файла")
                return
            
            submission_data['data']['media_path'] = media_path
            submission_data['step'] = 'enter_result'
            
            # Ask for result based on challenge type
            challenge_type = submission_data['data']['challenge_type']
            result_prompt = self._get_result_prompt(challenge_type)
            
            # Create persistent keyboard
            def create_persistent_keyboard():
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
                markup.row('🏃 Регистрация', '🎉 События')
                markup.row('🏆 Челленджи', '📊 Статистика')
                markup.row('ℹ️ Помощь', '🏠 Главное меню')
                return markup
            
            markup = create_persistent_keyboard()
            safe_send_message(self.bot, 
                chat_id,
                f"Файл загружен ✅\n\n{result_prompt}",
                reply_markup=markup
            )
            
        except Exception as e:
            logger.error(f"Media upload error: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при загрузке файла")
    
    def _handle_challenge_selection(self, chat_id: int, text: str):
        """Handle challenge selection"""
        db = self.db_manager.get_session()
        try:
            # Extract challenge name from button text
            challenge_name = text.split(' - ', 1)[1] if ' - ' in text else text
            
            # Find challenge
            challenge = db.query(Challenge).filter(
                Challenge.name == challenge_name,
                Challenge.is_active == True
            ).first()
            
            if not challenge:
                safe_send_message(self.bot, chat_id, "Выбранный челлендж не найден")
                return
            
            self.active_submissions[chat_id]['data']['challenge_id'] = challenge.id
            self.active_submissions[chat_id]['data']['challenge_type'] = challenge.challenge_type
            self.active_submissions[chat_id]['step'] = 'upload_media'
            
            # Ask for media upload
            instruction = self._get_media_instruction(challenge.challenge_type)
            
            # Create persistent keyboard
            def create_persistent_keyboard():
                markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
                markup.row('🏃 Регистрация', '🎉 События')
                markup.row('🏆 Челленджи', '📊 Статистика')
                markup.row('ℹ️ Помощь', '🏠 Главное меню')
                return markup
            
            markup = create_persistent_keyboard()
            safe_send_message(self.bot, 
                chat_id,
                f"*{challenge.name}*\n\n{instruction}",
                parse_mode='Markdown',
                reply_markup=markup
            )
            
        except Exception as e:
            logger.error(f"Challenge selection error: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при выборе челленджа")
        finally:
            db.close()
    
    def _handle_result_input(self, chat_id: int, text: str):
        """Handle result input"""
        try:
            # Parse numeric result
            result_value = float(text.replace(',', '.'))
            
            if result_value <= 0:
                safe_send_message(self.bot, chat_id, "Результат должен быть положительным числом")
                return
            
            self.active_submissions[chat_id]['data']['result_value'] = result_value
            self.active_submissions[chat_id]['step'] = 'enter_comment'
            
            safe_send_message(self.bot, 
                chat_id,
                "Добавьте комментарий к своему результату (или отправьте '-' для пропуска):"
            )
            
        except ValueError:
            safe_send_message(self.bot, chat_id, "Пожалуйста, введите числовое значение")
    
    def _handle_comment_input(self, chat_id: int, text: str):
        """Handle comment input and complete submission"""
        if text != '-':
            self.active_submissions[chat_id]['data']['comment'] = text
        
        self._complete_submission(chat_id)
    
    def _complete_submission(self, chat_id: int):
        """Complete the submission process"""
        submission_session = self.active_submissions[chat_id]
        submission_data = submission_session['data']
        participant_id = submission_session['participant_id']
        
        # Add participant_id to data for validation
        submission_data['participant_id'] = participant_id
        
        # Validate required fields
        required_fields = ['participant_id', 'challenge_id', 'result_value']
        missing_fields = [field for field in required_fields if field not in submission_data or not submission_data[field]]
        
        if missing_fields:
            error_msg = f"Отсутствуют обязательные данные: {', '.join(missing_fields)}"
            logger.error(f"Missing fields in submission: {missing_fields}")
            logger.error(f"Submission data: {submission_data}")
            logger.error(f"Submission session: {submission_session}")
            safe_send_message(self.bot, chat_id, error_msg)
            return
        
        db = self.db_manager.get_session()
        try:
            # Create submission record
            submission = Submission(
                participant_id=submission_data['participant_id'],
                challenge_id=submission_data['challenge_id'],
                media_path=submission_data.get('media_path'),
                result_value=submission_data.get('result_value'),
                result_unit=self._get_result_unit(submission_data['challenge_type']),
                comment=submission_data.get('comment'),
                status=SubmissionStatus.PENDING
            )
            
            db.add(submission)
            db.commit()
            
            # Success message
            safe_send_message(self.bot, 
                chat_id,
                "✅ *Отчет успешно отправлен!*\n\n"
                "Ваш отчет находится на модерации.\n"
                "Статус проверки вы сможете увидеть в своей статистике.",
                parse_mode='Markdown'
            )
            
            logger.info(f"New submission from participant {submission_data['participant_id']}")
            
        except Exception as e:
            db.rollback()
            logger.error(f"Submission database error: {e}")
            logger.error(f"Submission data: {submission_data}")
            # Send detailed error message
            error_msg = f"Ошибка при сохранении отчета:\n{str(e)}\n\nПожалуйста, попробуйте позже или обратитесь к администратору."
            safe_send_message(self.bot, chat_id, error_msg)
        finally:
            db.close()
            # Clean up
            if chat_id in self.active_submissions:
                del self.active_submissions[chat_id]
    
    def show_user_stats(self, chat_id: int):
        """Show user statistics"""
        db = self.db_manager.get_session()
        try:
            # Get participant
            participant = db.query(Participant).filter(
                Participant.telegram_id == str(chat_id)
            ).first()
            
            if not participant:
                safe_send_message(self.bot, 
                    chat_id,
                    "Для просмотра статистики необходимо зарегистрироваться в RunBot!\n"
                    "Используйте команду /register"
                )
                return
            
            # Get submissions
            submissions = db.query(Submission).filter(
                Submission.participant_id == participant.id
            ).order_by(Submission.submission_date.desc()).limit(10).all()
            
            # Create stats message
            message = f"*📊 Ваша статистика*\n\n"
            message += f"🏁 Стартовый номер: {participant.start_number}\n"
            message += f"📈 Всего отчетов: {len(submissions)}\n\n"
            
            if submissions:
                message += "*Последние отчеты:*\n"
                for sub in submissions[:5]:  # Show last 5
                    challenge = db.query(Challenge).get(sub.challenge_id)
                    status_icon = {
                        SubmissionStatus.PENDING: "⏳",
                        SubmissionStatus.APPROVED: "✅",
                        SubmissionStatus.REJECTED: "❌"
                    }.get(sub.status, "❓")
                    
                    message += (
                        f"{status_icon} {challenge.name}\n"
                        f"   Результат: {sub.result_value} {sub.result_unit}\n"
                        f"   Дата: {sub.submission_date.strftime('%d.%m.%Y %H:%M')}\n\n"
                    )
            else:
                message += "У вас пока нет отчетов"
            
            safe_send_message(self.bot, chat_id, message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Error showing stats: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении статистики")
        finally:
            db.close()
    
    def _get_challenge_type_display(self, challenge_type: ChallengeType) -> str:
        """Get display name for challenge type"""
        mapping = {
            ChallengeType.PUSH_UPS: "💪 Отжимания",
            ChallengeType.SQUATS: "🦵 Приседания",
            ChallengeType.PLANK: "🧘 Планка",
            ChallengeType.RUNNING: "🏃 Бег",
            ChallengeType.STEPS: "👣 Шаги"
        }
        return mapping.get(challenge_type, challenge_type.value)
    
    def _get_media_instruction(self, challenge_type: ChallengeType) -> str:
        """Get media upload instructions based on challenge type"""
        instructions = {
            ChallengeType.RUNNING: "Пришлите скриншот из приложения для бега (Strava, Garmin, и т.д.)",
            ChallengeType.STEPS: "Пришлите скриншот счетчика шагов",
            ChallengeType.PUSH_UPS: "Пришлите видео выполнения отжиманий",
            ChallengeType.SQUATS: "Пришлите видео выполнения приседаний",
            ChallengeType.PLANK: "Пришлите видео удержания планки"
        }
        return instructions.get(challenge_type, "Пришлите подтверждение выполнения задания")
    
    def _get_result_prompt(self, challenge_type: ChallengeType) -> str:
        """Get result input prompt based on challenge type"""
        prompts = {
            ChallengeType.PUSH_UPS: "Введите количество повторений:",
            ChallengeType.SQUATS: "Введите количество повторений:",
            ChallengeType.PLANK: "Введите время в секундах:",
            ChallengeType.RUNNING: "Введите дистанцию в километрах:",
            ChallengeType.STEPS: "Введите количество шагов:"
        }
        return prompts.get(challenge_type, "Введите результат:")
    
    def _get_result_unit(self, challenge_type: ChallengeType) -> str:
        """Get result unit based on challenge type"""
        units = {
            ChallengeType.PUSH_UPS: "повторений",
            ChallengeType.SQUATS: "повторений",
            ChallengeType.PLANK: "секунд",
            ChallengeType.RUNNING: "км",
            ChallengeType.STEPS: "шагов"
        }
        return units.get(challenge_type, "единиц")
    
    def _save_media(self, message) -> Optional[str]:
        """Save uploaded media file using StorageManager"""
        try:
            import uuid
            from pathlib import Path
            from io import BytesIO

            # Handle different media types
            if message.photo:
                file_info = self.bot.get_file(message.photo[-1].file_id)
                file_extension = ".jpg"
                content_type = "image/jpeg"
            elif message.video:
                file_info = self.bot.get_file(message.video.file_id)
                file_extension = ".mp4"
                content_type = "video/mp4"
            elif message.document:
                file_info = self.bot.get_file(message.document.file_id)
                file_extension = Path(message.document.file_name).suffix or ".dat"
                content_type = message.document.mime_type or "application/octet-stream"
            else:
                return None

            # Generate unique filename
            filename = f"{uuid.uuid4()}{file_extension}"

            # Download file
            downloaded_file = self.bot.download_file(file_info.file_path)

            # Create a simple file-like object with required attributes
            class FileLikeObject(BytesIO):
                def __init__(self, data, filename, content_type):
                    super().__init__(data)
                    self.filename = filename
                    self.content_type = content_type

            file_obj = FileLikeObject(downloaded_file, filename, content_type)

            # Upload using StorageManager
            storage = get_storage_manager()
            result = storage.upload_file(file_obj, filename)

            logger.info(f"File uploaded to storage: {result['path']} ({result['size_mb']:.2f}MB)")
            return result['path']

        except Exception as e:
            logger.error(f"Error saving media: {e}")
            return None

    def show_challenge_participants(self, chat_id: int, challenge_id: int):
        """Show list of participants registered for specific challenge (for admin panel)"""
        db = self.db_manager.get_session()
        try:
            # Get challenge
            challenge = db.query(Challenge).get(challenge_id)
            if not challenge:
                safe_send_message(self.bot, chat_id, "Челлендж не найден")
                return

            # Get participants registered for this challenge through ChallengeRegistration
            # This shows ALL registered participants, not just those who submitted reports
            registrations = db.query(ChallengeRegistration, Participant).join(Participant).filter(
                ChallengeRegistration.challenge_id == challenge_id,
                ChallengeRegistration.is_active == True
            ).order_by(ChallengeRegistration.registration_date.desc()).all()

            if not registrations:
                safe_send_message(self.bot, chat_id, f"На челлендж *{challenge.name}* пока никто не зарегистрировался", parse_mode='Markdown')
                return

            # Create message
            message = f"*👥 Участники челленджа: {challenge.name}*\n\n"
            
            for i, (registration, participant) in enumerate(registrations, 1):
                # Get participant's distance type if applicable
                distance_info = ""
                if participant.distance_type:
                    distance_name = "Взрослый забег" if participant.distance_type == DistanceType.ADULT_RUN else "Детский забег"
                    distance_info = f" | {distance_name}"
                
                # Check if participant has submitted reports
                submission_count = db.query(Submission).filter(
                    Submission.participant_id == participant.id,
                    Submission.challenge_id == challenge_id
                ).count()
                
                # Get latest submission status if exists
                latest_submission = db.query(Submission).filter(
                    Submission.participant_id == participant.id,
                    Submission.challenge_id == challenge_id
                ).order_by(Submission.submission_date.desc()).first()
                
                submission_info = f"📊 Отчетов: {submission_count}"
                if latest_submission:
                    status_icon = {
                        SubmissionStatus.PENDING: "⏳",
                        SubmissionStatus.APPROVED: "✅",
                        SubmissionStatus.REJECTED: "❌"
                    }.get(latest_submission.status, "❓")
                    submission_info += f" | Последний: {status_icon} {latest_submission.result_value} {latest_submission.result_unit}"
                else:
                    submission_info += " | Нет отчетов"
                
                message += (
                    f"{i}. `{participant.start_number}` - {participant.full_name}\n"
                    f"   📞 {participant.phone} | 📅 {registration.registration_date.strftime('%d.%m.%Y')}\n"
                    f"   🏷️ Номер в челлендже: {registration.bib_number}{distance_info}\n"
                    f"   {submission_info}\n\n"
                )
            
            message += f"📊 Всего участников: {len(registrations)}"

            # Add navigation button
            markup = telebot.types.InlineKeyboardMarkup()
            markup.row(
                telebot.types.InlineKeyboardButton("🔙 Назад", callback_data="participants_menu")
            )

            safe_send_message(self.bot, chat_id, message, parse_mode='Markdown', reply_markup=markup)
            
        except Exception as e:
            logger.error(f"Error showing challenge participants: {e}")
            safe_send_message(self.bot, chat_id, "Ошибка при получении списка участников")
        finally:
            db.close()

    def handle_callback_query(self, call):
        """Handle callback queries for challenges"""
        try:
            callback_data = call.data
            logger.info(f"Challenge manager handling callback: {callback_data} from {call.from_user.id}")

            # Handle challenge type filters
            if callback_data == 'challenges_all':
                self.bot.answer_callback_query(call.id, "Показываю все челленджи")
                self.show_active_challenges(call.message.chat.id, challenge_type=None)
            elif callback_data == 'challenges_push_ups':
                self.bot.answer_callback_query(call.id, "Показываю отжимания")
                self.show_active_challenges(call.message.chat.id, challenge_type=ChallengeType.PUSH_UPS)
            elif callback_data == 'challenges_squats':
                self.bot.answer_callback_query(call.id, "Показываю приседания")
                self.show_active_challenges(call.message.chat.id, challenge_type=ChallengeType.SQUATS)
            elif callback_data == 'challenges_plank':
                self.bot.answer_callback_query(call.id, "Показываю планку")
                self.show_active_challenges(call.message.chat.id, challenge_type=ChallengeType.PLANK)
            elif callback_data == 'challenges_running':
                self.bot.answer_callback_query(call.id, "Показываю бег")
                self.show_active_challenges(call.message.chat.id, challenge_type=ChallengeType.RUNNING)
            elif callback_data == 'challenges_steps':
                self.bot.answer_callback_query(call.id, "Показываю шаги")
                self.show_active_challenges(call.message.chat.id, challenge_type=ChallengeType.STEPS)
            # Handle challenge participation
            elif callback_data.startswith('challenge_join_'):
                challenge_id = int(callback_data.split('_')[2])
                self.bot.answer_callback_query(call.id)
                self.register_for_challenge(call.message.chat.id, challenge_id)
            # Handle submission
            elif callback_data.startswith('challenge_submit_'):
                challenge_id = int(callback_data.split('_')[2])
                self.bot.answer_callback_query(call.id)
                self.start_submission(call.message.chat.id, challenge_id)
            # Handle challenge stats
            elif callback_data.startswith('challenge_stats_'):
                challenge_id = int(callback_data.split('_')[2])
                self.bot.answer_callback_query(call.id, "Получаю статистику...")
                self.show_challenge_leaderboard(call.message.chat.id, challenge_id)
            # Handle challenge participants (for admin panel)
            elif callback_data.startswith('challenge_participants_'):
                challenge_id = int(callback_data.split('_')[2])
                self.bot.answer_callback_query(call.id, "Получаю список участников...")
                self.show_challenge_participants(call.message.chat.id, challenge_id)
            # Handle already submitted notification
            elif callback_data == 'challenge_already_submitted':
                self.bot.answer_callback_query(call.id, "Вы уже отправляли отчет сегодня")
            # Handle submit report button
            elif callback_data == 'submit_report':
                self.bot.answer_callback_query(call.id)
                self.start_submission_process(call.message.chat.id)
            else:
                self.bot.answer_callback_query(call.id, "Неизвестная команда")

        except Exception as e:
            logger.error(f"Error handling challenge callback: {e}")
            import traceback
            traceback.print_exc()
            self.bot.answer_callback_query(call.id, "Ошибка обработки запроса")