"""
Reminder Service

Background service that polls the database for due reminders and sends them
via Telegram.
"""

import asyncio
import logging
from datetime import timedelta, timezone
from typing import Optional

from telegram import Bot
from telegram.error import TelegramError

from services.reminder_service.database import ReminderDatabaseService
from shared.models.reminder import format_recurring_pattern_display

logger = logging.getLogger(__name__)


def _format_in_user_tz(dt, tz_str: str) -> str:
    """Format datetime in user's timezone for logging (e.g. '20:53 GMT+3')."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Parse GMT+3 -> UTC+3
    offset_hours = 3
    if tz_str:
        tz_lower = tz_str.upper().replace("GMT", "UTC")
        if "+" in tz_lower:
            try:
                offset_hours = int(tz_lower.split("+")[1].strip()[:2])
            except (ValueError, IndexError):
                pass
        elif "-" in tz_lower and "UTC" in tz_lower:
            try:
                offset_hours = -int(tz_lower.split("-")[1].strip()[:2])
            except (ValueError, IndexError):
                pass
    user_tz = timezone(timedelta(hours=offset_hours))
    local = dt.astimezone(user_tz)
    return f"{local.strftime('%H:%M')} {tz_str or 'UTC'}"



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
        poll_count = 0
        logger.info("Poll loop started (interval=%ds)", self.poll_interval)
        while self._running:
            poll_count += 1
            if poll_count == 1 or poll_count % 10 == 0:
                logger.info("Poll #%d: checking for due reminders", poll_count)
            try:
                await self._process_due_reminders()
            except Exception as e:
                logger.error(f"Error in reminder polling loop (poll #%d): {e}", poll_count, exc_info=True)

            # Wait before next poll
            try:
                logger.debug("Sleeping %ds until next poll", self.poll_interval)
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                logger.info("Poll loop cancelled (total polls: %d)", poll_count)
                break

    async def _process_due_reminders(self) -> None:
        """Process all due reminders."""
        try:
            # Log all reminders once per poll (for debugging)
            all_reminders = await self.database_service.get_all_reminders_for_logging()
            if all_reminders:
                lines = [
                    f"  id={r.id} user_id={r.user_id} due={r.reminder_date} sent={r.sent} msg={r.message[:40]}..."
                    if len(r.message) > 40
                    else f"  id={r.id} user_id={r.user_id} due={r.reminder_date} sent={r.sent} msg={r.message}"
                    for r in all_reminders
                ]
                logger.info("All reminders (%d):\n%s", len(all_reminders), "\n".join(lines))
            else:
                logger.info("All reminders: 0 (empty table)")

            due_reminders = await self.database_service.get_due_reminders()

            if not due_reminders:
                logger.debug("No due reminders found")
                return

            logger.info("Processing %d due reminder(s)", len(due_reminders))
            for reminder in due_reminders:
                try:
                    logger.info(
                        "Sending reminder id=%s to user_id=%s (due=%s)",
                        reminder.id,
                        reminder.user_id,
                        reminder.reminder_date,
                    )
                    await self._send_reminder(reminder)
                except Exception as e:
                    logger.error(
                        "Failed to send reminder id=%s to user_id=%s: %s",
                        reminder.id,
                        reminder.user_id,
                        e,
                        exc_info=True,
                    )
        except Exception as e:
            logger.error("Failed to get due reminders: %s", e, exc_info=True)

    async def _send_reminder(self, reminder) -> None:
        """
        Send a reminder via Telegram and handle recurring reminders.

        Args:
            reminder: ReminderRecord to send
        """
        try:
            # Format reminder message
            message = self._format_reminder_message(reminder)
            logger.debug("Formatted message for reminder %s: %s", reminder.id, message[:80])

            # Send via Telegram
            logger.info("Sending Telegram message to chat_id=%s...", reminder.user_id)
            await self.telegram_bot.send_message(
                chat_id=reminder.user_id, text=message, parse_mode="HTML"
            )

            logger.info("Successfully sent reminder id=%s to user_id=%s", reminder.id, reminder.user_id)

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
                    # Log in user's timezone for clarity (stored as UTC in DB)
                    user_tz_str = _format_in_user_tz(next_date, reminder.timezone)
                    logger.info(
                        "Created next occurrence for recurring reminder %s at %s (%s)",
                        reminder.id,
                        next_date,
                        user_tz_str,
                    )
                else:
                    logger.warning(
                        f"Could not calculate next date for recurring "
                        f"reminder {reminder.id} with pattern "
                        f"{reminder.recurring_pattern}"
                    )

        except TelegramError as e:
            logger.error(
                "Telegram error sending reminder id=%s to user_id=%s: %s (message=%s)",
                reminder.id,
                reminder.user_id,
                e,
                str(e),
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
            disp = format_recurring_pattern_display(reminder.recurring_pattern)
            if disp:
                message += f"\n\n🔄 Повторяющееся: {disp}"

        return message
