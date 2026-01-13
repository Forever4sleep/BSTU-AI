#!/usr/bin/env python3
"""
Reminder Service Main Entry Point

Standalone microservice that polls the database for due reminders
and sends them via Telegram Bot API.

Usage:
    python -m services.reminder_service.main
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

import asyncpg
from telegram import Bot

# Add project root to path to import shared modules
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.database import create_connection_pool, ensure_reminders_table
from services.reminder_service.config import (
    get_database_url,
    get_poll_interval,
    get_telegram_token,
)
from services.reminder_service.database import ReminderDatabaseService
from services.reminder_service.service import ReminderService

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


class ReminderServiceApp:
    """Main application class for the reminder service."""

    def __init__(self):
        """Initialize the reminder service application."""
        self.database_pool: Optional[asyncpg.Pool] = None
        self.reminder_service: Optional[ReminderService] = None
        self._shutdown_event = asyncio.Event()

    async def initialize(self) -> None:
        """Initialize database and reminder service."""
        try:
            # Get configuration
            database_url = get_database_url()
            telegram_token = get_telegram_token()
            poll_interval = get_poll_interval()

            logger.info("Initializing reminder service...")

            # Create database connection pool
            logger.info("Connecting to database...")
            self.database_pool = await create_connection_pool(
                database_url=database_url
            )
            await ensure_reminders_table(self.database_pool)

            # Initialize database service
            database_service = ReminderDatabaseService(self.database_pool)

            # Initialize Telegram bot
            telegram_bot = Bot(token=telegram_token)

            # Initialize reminder service
            self.reminder_service = ReminderService(
                database_service=database_service,
                telegram_bot=telegram_bot,
                poll_interval=poll_interval,
            )

            logger.info("Reminder service initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize reminder service: {e}", exc_info=True)
            raise

    async def start(self) -> None:
        """Start the reminder service."""
        if not self.reminder_service:
            raise RuntimeError("Service not initialized. Call initialize() first.")

        logger.info("Starting reminder service...")
        await self.reminder_service.start()

    async def stop(self) -> None:
        """Stop the reminder service."""
        logger.info("Stopping reminder service...")

        if self.reminder_service:
            await self.reminder_service.stop()

        if self.database_pool:
            await self.database_pool.close()

        logger.info("Reminder service stopped")

    async def run(self) -> None:
        """Run the service until shutdown signal."""
        # Set up signal handlers
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._signal_handler)

        try:
            # Wait for shutdown signal
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def _signal_handler(self) -> None:
        """Handle shutdown signals."""
        logger.info("Received shutdown signal")
        self._shutdown_event.set()


async def main():
    """Main entry point."""
    app = ReminderServiceApp()

    try:
        await app.initialize()
        await app.start()
        await app.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
