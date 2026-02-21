"""
Database Service for Scheduler Agent

Handles all database operations for reminders.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

import asyncpg

from shared.models.reminder import ReminderCreate, ReminderRecord

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

    async def create_reminder(self, reminder: ReminderCreate) -> UUID:
        """
        Create a new reminder in the database.

        Args:
            reminder: ReminderCreate model with reminder data

        Returns:
            UUID of the created reminder

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        query = """
        INSERT INTO reminders (
            user_id, message, reminder_date, timezone,
            recurring_pattern
        )
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                reminder_id = await conn.fetchval(
                    query,
                    reminder.user_id,
                    reminder.message,
                    reminder.reminder_date,
                    reminder.timezone or "GMT+3",
                    reminder.get_recurring_pattern_for_db(),
                )
                logger.info(
                    f"Created reminder {reminder_id} for user {reminder.user_id} "
                    f"at {reminder.reminder_date}"
                )
                return reminder_id
        except Exception as e:
            logger.error(f"Failed to create reminder: {e}")
            raise

    async def create_reminders(self, reminders: List[ReminderCreate]) -> List[UUID]:
        """
        Create multiple reminders in the database in a single transaction.

        Args:
            reminders: List of ReminderCreate models with reminder data

        Returns:
            List of UUIDs of the created reminders

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        query = """
        INSERT INTO reminders (
            user_id, message, reminder_date, timezone,
            recurring_pattern
        )
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
        """

        try:
            reminder_ids = []
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for reminder in reminders:
                        reminder_id = await conn.fetchval(
                            query,
                            reminder.user_id,
                            reminder.message,
                            reminder.reminder_date,
                            reminder.timezone or "GMT+3",
                            reminder.get_recurring_pattern_for_db(),
                        )
                        reminder_ids.append(reminder_id)
                        logger.info(
                            f"Created reminder {reminder_id} for user {reminder.user_id} "
                            f"at {reminder.reminder_date}"
                        )
            logger.info(
                f"Created {len(reminder_ids)} reminders for user {reminders[0].user_id if reminders else 'unknown'}"
            )
            return reminder_ids
        except Exception as e:
            logger.error(f"Failed to create reminders: {e}")
            raise

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
        # reminder_date is timestamptz (UTC). Compare directly with NOW().
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
                    logger.info(f"Found {len(reminders)} due reminders")
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
                await conn.execute(query, reminder_id)
                logger.debug(f"Marked reminder {reminder_id} as sent")
        except Exception as e:
            logger.error(f"Failed to mark reminder {reminder_id} as sent: {e}")
            raise

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
        # Ensure we work in UTC for consistent calculation
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

    async def get_user_reminders(
        self, user_id: int, limit: int = 5
    ) -> List[ReminderRecord]:
        """
        Get all reminders for a specific user (up to limit).

        Args:
            user_id: Telegram user ID
            limit: Maximum number of reminders to return (default: 5)

        Returns:
            List of ReminderRecord objects for the user

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        query = """
        SELECT id, user_id, message, reminder_date, timezone,
               recurring_pattern, sent, created_at, updated_at
        FROM reminders
        WHERE user_id = $1 AND sent = FALSE
        ORDER BY reminder_date ASC
        LIMIT $2
        """

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(query, user_id, limit)
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
                return reminders
        except Exception as e:
            logger.error(f"Failed to get reminders for user {user_id}: {e}")
            raise

    async def get_reminder_by_id(
        self, reminder_id: UUID, user_id: int
    ) -> Optional[ReminderRecord]:
        """
        Get a specific reminder by ID for a user.

        Args:
            reminder_id: UUID of the reminder
            user_id: Telegram user ID (for security - ensures user owns the reminder)

        Returns:
            ReminderRecord if found, None otherwise

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        query = """
        SELECT id, user_id, message, reminder_date, timezone,
               recurring_pattern, sent, created_at, updated_at
        FROM reminders
        WHERE id = $1 AND user_id = $2
        """

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(query, reminder_id, user_id)
                if not row:
                    return None

                return ReminderRecord(
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
        except Exception as e:
            logger.error(f"Failed to get reminder {reminder_id}: {e}")
            raise

    async def update_reminder(
        self,
        reminder_id: UUID,
        user_id: int,
        message: Optional[str] = None,
        reminder_date: Optional[datetime] = None,
        timezone: Optional[str] = None,
        recurring_pattern: Optional[str] = None,
    ) -> bool:
        """
        Update an existing reminder.

        Args:
            reminder_id: UUID of the reminder to update
            user_id: Telegram user ID (for security)
            message: New message text (if provided)
            reminder_date: New reminder date (if provided)
            timezone: New timezone (if provided)
            recurring_pattern: New recurring pattern (if provided)

        Returns:
            True if reminder was updated, False if not found

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        # Build update query dynamically based on provided fields
        updates = []
        params = []
        param_idx = 1

        if message is not None:
            updates.append(f"message = ${param_idx}")
            params.append(message)
            param_idx += 1

        if reminder_date is not None:
            updates.append(f"reminder_date = ${param_idx}")
            params.append(reminder_date)
            param_idx += 1

        if timezone is not None:
            updates.append(f"timezone = ${param_idx}")
            params.append(timezone)
            param_idx += 1

        if recurring_pattern is not None:
            updates.append(f"recurring_pattern = ${param_idx}")
            params.append(recurring_pattern)
            param_idx += 1

        if not updates:
            return False  # Nothing to update

        updates.append(f"updated_at = NOW()")
        params.append(reminder_id)
        params.append(user_id)

        query = f"""
        UPDATE reminders
        SET {', '.join(updates)}
        WHERE id = ${param_idx} AND user_id = ${param_idx + 1}
        RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, *params)
                if result:
                    logger.info(f"Updated reminder {reminder_id} for user {user_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to update reminder {reminder_id}: {e}")
            raise

    async def delete_reminder(self, reminder_id: UUID, user_id: int) -> bool:
        """
        Delete a reminder.

        Args:
            reminder_id: UUID of the reminder to delete
            user_id: Telegram user ID (for security)

        Returns:
            True if reminder was deleted, False if not found

        Raises:
            asyncpg.exceptions.PostgresError: If database operation fails
        """
        query = """
        DELETE FROM reminders
        WHERE id = $1 AND user_id = $2
        RETURNING id
        """

        try:
            async with self.pool.acquire() as conn:
                result = await conn.fetchval(query, reminder_id, user_id)
                if result:
                    logger.info(f"Deleted reminder {reminder_id} for user {user_id}")
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to delete reminder {reminder_id}: {e}")
            raise
