"""
Reminder Service

Background service that polls the database for due reminders and sends them
via Telegram.
"""

import asyncio
import logging
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from agents.scheduler.database import ReminderDatabaseService

logger = logging.getLogger(__name__)


class ReminderService:
    """Background service that polls for due reminders and sends them via Telegram."""

    def __init__(
        self,
        database_service: ReminderDatabaseService,
        telegram_bot: Bot,
        poll_interval: int = 60,
    ):
        """
        Initialize the reminder service.

        Args:
            database_service: ReminderDatabaseService instance
            telegram_bot: Telegram Bot instance for sending messages
            poll_interval: Interval in seconds between database polls (default: 60)
        """
        self.database_service = database_service
        self.telegram_bot = telegram_bot
        self.poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the reminder service background task."""
        if self._running:
            logger.warning("Reminder service is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(
            f"Started reminder service (poll interval: {self.poll_interval}s)"
        )

    async def stop(self) -> None:
        """Stop the reminder service background task."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped reminder service")

    async def _poll_loop(self) -> None:
        """Main polling loop that checks for due reminders."""
        while self._running:
            try:
                await self._process_due_reminders()
            except Exception as e:
                logger.error(f"Error in reminder polling loop: {e}", exc_info=True)

            # Wait before next poll
            try:
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break

    async def _process_due_reminders(self) -> None:
        """Process all due reminders."""
        try:
            due_reminders = await self.database_service.get_due_reminders()

            for reminder in due_reminders:
                try:
                    await self._send_reminder(reminder)
                except Exception as e:
                    logger.error(
                        f"Failed to send reminder {reminder.id}: {e}",
                        exc_info=True,
                    )
        except Exception as e:
            logger.error(f"Failed to get due reminders: {e}", exc_info=True)

    async def _send_reminder(self, reminder) -> None:
        """
        Send a reminder via Telegram and handle recurring reminders.

        Args:
            reminder: ReminderRecord to send
        """
        try:
            # Format reminder message
            message = self._format_reminder_message(reminder)

            # Send via Telegram
            await self.telegram_bot.send_message(
                chat_id=reminder.user_id, text=message
            )

            logger.info(f"Sent reminder {reminder.id} to user {reminder.user_id}")

            # Mark as sent
            await self.database_service.mark_reminder_sent(reminder.id)

            # Handle recurring reminders
            if reminder.recurring_pattern:
                next_date = await self.database_service.get_next_recurring_date(
                    reminder
                )
                if next_date:
                    await self.database_service.update_recurring_reminder(
                        reminder.id, next_date
                    )
                    logger.info(
                        f"Created next occurrence for recurring reminder "
                        f"{reminder.id} at {next_date}"
                    )
                else:
                    logger.warning(
                        f"Could not calculate next date for recurring "
                        f"reminder {reminder.id} with pattern "
                        f"{reminder.recurring_pattern}"
                    )

        except TelegramError as e:
            logger.error(
                f"Telegram error sending reminder {reminder.id}: {e}",
                exc_info=True,
            )
            # Still mark as sent to avoid retrying indefinitely
            # In production, you might want to implement retry logic
            await self.database_service.mark_reminder_sent(reminder.id)
        except Exception as e:
            logger.error(
                f"Unexpected error sending reminder {reminder.id}: {e}",
                exc_info=True,
            )
            raise

    def _format_reminder_message(self, reminder) -> str:
        """
        Format a reminder message for Telegram.

        Args:
            reminder: ReminderRecord to format

        Returns:
            Formatted message string
        """
        message = f"🔔 <b>Напоминание</b>\n\n{reminder.message}"

        if reminder.recurring_pattern:
            message += f"\n\n🔄 Повторяющееся: {reminder.recurring_pattern}"

        return message
