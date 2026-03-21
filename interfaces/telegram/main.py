"""
Main entry point for Telegram Bot

Run this script to start the Telegram bot.
"""

import asyncio
import logging
import sys

from interfaces.telegram.bot import TelegramBot
from config import get_telegram_token

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def main():
    """Main function to start the Telegram bot."""
    try:
        # Get bot token
        token = get_telegram_token()

        # Create and run bot
        bot = TelegramBot(token)
        logger.info("Starting Telegram bot...")
        bot.run()

    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        logger.info(
            "Please create a .env file with TELEGRAM_BOT_TOKEN=your_token_here"
        )
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Error running bot: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
