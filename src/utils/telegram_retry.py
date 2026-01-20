"""
Telegram API retry wrapper для обработки сетевых ошибок
"""
import time
import logging
from functools import wraps
from typing import Callable, Any
import requests
from telebot.apihelper import ApiException

logger = logging.getLogger(__name__)


def telegram_retry(max_retries: int = 3, delay: float = 1.0, backoff: float = 2.0):
    """
    Декоратор для автоматического retry Telegram API запросов при сетевых ошибках

    Args:
        max_retries: Максимальное количество попыток
        delay: Начальная задержка между попытками (секунды)
        backoff: Множитель увеличения задержки (экспоненциальный backoff)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            current_delay = delay
            last_exception = None

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)

                except (requests.exceptions.ConnectionError,
                        requests.exceptions.Timeout,
                        ConnectionResetError,
                        ConnectionRefusedError,
                        BrokenPipeError) as e:

                    last_exception = e

                    # Не повторяем попытки для критических ошибок API
                    if isinstance(e, ApiException):
                        if e.result_json.get('error_code') in [401, 403, 404]:
                            raise

                    if attempt < max_retries - 1:
                        logger.warning(
                            f"Telegram API error (attempt {attempt + 1}/{max_retries}): "
                            f"{type(e).__name__}: {str(e)[:100]}. "
                            f"Retrying in {current_delay:.1f}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Telegram API error after {max_retries} attempts: "
                            f"{type(e).__name__}: {str(e)[:100]}"
                        )

            # Если все попытки исчерпаны, пробрасываем исключение
            raise last_exception

        return wrapper
    return decorator


def safe_send_message(bot, chat_id: int, text: str, **kwargs):
    """
    Безопасная отправка сообщения с автоматическим retry
    """
    @telegram_retry(max_retries=3, delay=1.0, backoff=2.0)
    def _send():
        return bot.send_message(chat_id, text, **kwargs)

    return _send()


def safe_edit_message(bot, chat_id: int, message_id: int, text: str, **kwargs):
    """
    Безопасное редактирование сообщения с автоматическим retry
    """
    @telegram_retry(max_retries=3, delay=1.0, backoff=2.0)
    def _edit():
        return bot.edit_message_text(text, chat_id, message_id, **kwargs)

    return _edit()


def safe_answer_callback(bot, callback_query_id: str, text: str = None, **kwargs):
    """
    Безопасный ответ на callback query с автоматическим retry
    """
    @telegram_retry(max_retries=3, delay=1.0, backoff=2.0)
    def _answer():
        return bot.answer_callback_query(callback_query_id, text, **kwargs)

    return _answer()


def safe_delete_message(bot, chat_id: int, message_id: int):
    """
    Безопасное удаление сообщения с автоматическим retry
    """
    @telegram_retry(max_retries=2, delay=0.5, backoff=2.0)
    def _delete():
        return bot.delete_message(chat_id, message_id)

    try:
        return _delete()
    except Exception as e:
        logger.warning(f"Could not delete message {message_id}: {e}")
        return None
