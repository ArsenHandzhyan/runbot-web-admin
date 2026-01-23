#!/usr/bin/env python3
"""
Simple test bot to log all incoming messages
"""
import os
import logging
from dotenv import load_dotenv
from telebot import TeleBot

# Load environment
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN not found")
        return

    logger.info(f"Starting test bot with token: ***{token[-10:]}")

    bot = TeleBot(token)

    @bot.message_handler(func=lambda message: True)
    def handle_all_messages(message):
        logger.info(f"Received message from {message.from_user.id}: '{message.text}'")
        if message.photo:
            logger.info(f"Received photo from {message.from_user.id}")
        elif message.video:
            logger.info(f"Received video from {message.from_user.id}")
        elif message.document:
            logger.info(f"Received document from {message.from_user.id}")
        else:
            logger.info(f"Message type: {message.content_type}")

        # Simple response
        try:
            bot.reply_to(message, f"Received: {message.text or 'media'}")
            logger.info(f"Replied to {message.from_user.id}")
        except Exception as e:
            logger.error(f"Error replying: {e}")

    logger.info("Bot starting polling...")
    try:
        bot.polling(none_stop=True, interval=0, timeout=20)
    except Exception as e:
        logger.error(f"Polling error: {e}")

if __name__ == "__main__":
    main()