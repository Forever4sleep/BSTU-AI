"""
Database Service for Reminder Service

Handles database operations for reminders.
This is a copy of the database service from agents/scheduler/database.py
to make the reminder service independent.
"""

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID

import asyncpg

# Add project root to path to import shared mчodules
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from shared.models.reminder import ReminderRecord

logger = logging.getLogger(__name__)


class ReminderDatabaseService:
    """Service for managing reminders in PostgreSQL database."""

    def __init__(self, pool: asyncpg.Pool):
        """
        Initialize the database service.

        Args:
            pool: AsyncPG connection pool
        """
        self.pool = pool

    async def get_all_reminders_for_logging(self, limit: int = 100) -> List[ReminderRecord]:
        """
        Get all reminders (sent and unsent) for logging. Ordered by reminder_date.

        Args:
            limit: Maximum number to return

        Returns:
            List of ReminderRecord objects
        """
        query = """
        SELECT id, user_id, message, reminder_date, timezone,
               recurring_pattern, sent, created_at, updated_at
        FROM reminders
        ORDER BY reminder_date ASC
        LIMIT $1
        """
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, limit)
                return [
                    ReminderRecord(
                        id=row["id"],
                        user_id=row["user_id"],
                        message=row["message"],
                        reminder_date=row["reminder_date"],
                        timezone=row["timezone"],
                        recurring_pattern=row["recurring_pattern"],
                        sent=row["sent"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]
        except Exception as e:
            logger.error("Failed to get reminders for logging: %s", e)
            return []

    async def get_due_reminders(self, limit: int = 100) -> List[ReminderRecord]:
        """
        Get all reminders that are due (reminder_date <= now() and sent = false).

        Args:
            limit: Maximum number of reminders to return

        Returns:
            List of ReminderRecord objects that are due

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        # reminder_date is stored as timestamptz (UTC). Compare directly with NOW().
        # The previous "NOW() AT TIME ZONE timezone" was incorrect: it mixed types
        # and "GMT+3" may not be a valid PostgreSQL timezone name.
        query = """
        SELECT id, user_id, message, reminder_date, timezone,
               recurring_pattern, sent, created_at, updated_at
        FROM reminders
        WHERE reminder_date <= NOW()
          AND sent = FALSE
        ORDER BY reminder_date ASC
        LIMIT $1
        """

        try:
            async with self.pool.acquire() as conn:
                # Log current DB time for debugging timezone issues
                db_now = await conn.fetchval("SELECT NOW()")
                total_unsent = await conn.fetchval(
                    "SELECT COUNT(*) FROM reminders WHERE sent = FALSE"
                )
                logger.debug(
                    "get_due_reminders: db NOW()=%s, total unsent reminders=%s",
                    db_now,
                    total_unsent,
                )

                rows = await conn.fetch(query, limit)
                reminders = [
                    ReminderRecord(
                        id=row["id"],
                        user_id=row["user_id"],
                        message=row["message"],
                        reminder_date=row["reminder_date"],
                        timezone=row["timezone"],
                        recurring_pattern=row["recurring_pattern"],
                        sent=row["sent"],
                        created_at=row["created_at"],
                        updated_at=row["updated_at"],
                    )
                    for row in rows
                ]

                if reminders:
                    logger.info(
                        "Found %d due reminder(s): %s",
                        len(reminders),
                        [(str(r.id), r.user_id, r.reminder_date) for r in reminders],
                    )
                else:
                    logger.info(
                        "No due reminders (db NOW=%s, unsent in DB=%s)",
                        db_now,
                        total_unsent,
                    )
                return reminders
        except Exception as e:
            logger.error(f"Failed to get due reminders: {e}")
            raise

    async def mark_reminder_sent(self, reminder_id: UUID) -> None:
        """
        Mark a reminder as sent.

        Args:
            reminder_id: UUID of the reminder to mark as sent

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        query = """
        UPDATE reminders
        SET sent = TRUE, updated_at = NOW()
        WHERE id = $1
        """

        try:
            async with self.pool.acquire() as conn:
                result = await conn.execute(query, reminder_id)
                logger.info("Marked reminder %s as sent (result=%s)", reminder_id, result)
        except Exception as e:
            logger.error(f"Failed to mark reminder {reminder_id} as sent: {e}")
            raise

    async def get_next_recurring_date(
        self, reminder: ReminderRecord
    ) -> Optional[datetime]:
        """
        Calculate the next occurrence date for a recurring reminder.

        Args:
            reminder: ReminderRecord with recurring pattern

        Returns:
            Next occurrence datetime, or None if pattern is invalid
        """
        if not reminder.recurring_pattern:
            return None

        pattern = reminder.recurring_pattern.lower()
        # Ensure we work in UTC: reminder_date from DB may be naive or in session TZ
        current_date = reminder.reminder_date
        if current_date.tzinfo is None:
            current_date = current_date.replace(tzinfo=timezone.utc)
        else:
            current_date = current_date.astimezone(timezone.utc)

        if pattern == "daily":
            return current_date + timedelta(days=1)
        elif pattern == "weekly":
            return current_date + timedelta(weeks=1)
        elif pattern == "monthly":
            # Add approximately one month (30 days)
            return current_date + timedelta(days=30)
        elif pattern.startswith("minutes:"):
            try:
                n = int(pattern.split(":")[1])
                if n > 0:
                    return current_date + timedelta(minutes=n)
            except (ValueError, IndexError):
                pass
            logger.warning(
                "Invalid minutes pattern: %s", reminder.recurring_pattern
            )
            return None
        else:
            logger.warning(
                f"Unknown recurring pattern: {reminder.recurring_pattern}"
            )
            return None

    async def update_recurring_reminder(
        self, reminder_id: UUID, next_date: datetime
    ) -> UUID:
        """
        Update a recurring reminder with the next occurrence date.

        Creates a new reminder record for the next occurrence and marks
        the current one as sent.

        Args:
            reminder_id: UUID of the current reminder
            next_date: Next occurrence date/time

        Returns:
            UUID of the newly created reminder record

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        # First, get the current reminder data
        get_query = """
        SELECT user_id, message, timezone, recurring_pattern
        FROM reminders
        WHERE id = $1
        """

        # Create new reminder for next occurrence
        insert_query = """
        INSERT INTO reminders (
            user_id, message, reminder_date, timezone,
            recurring_pattern
        )
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # Get current reminder data
                    row = await conn.fetchrow(get_query, reminder_id)
                    if not row:
                        raise ValueError(f"Reminder {reminder_id} not found")

                    # Mark current reminder as sent
                    await self.mark_reminder_sent(reminder_id)

                    # Create new reminder for next occurrence
                    new_reminder_id = await conn.fetchval(
                        insert_query,
                        row["user_id"],
                        row["message"],
                        next_date,
                        row["timezone"],
                        row["recurring_pattern"],
                    )

                    logger.info(
                        f"Created next occurrence {new_reminder_id} for "
                        f"recurring reminder {reminder_id} at {next_date}"
                    )
                    return new_reminder_id
        except Exception as e:
            logger.error(
                f"Failed to update recurring reminder {reminder_id}: {e}"
            )
            raise
