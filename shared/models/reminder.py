"""
Reminder Models

Pydantic models for reminder structured output and data representation.
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class RecurringPattern(str, Enum):
    """Recurring reminder patterns."""

    NOT_SPECIFIED = "NOT SPECIFIED"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    EVERY_MINUTES = "minutes"  # Use with recurring_interval_minutes


class ReminderCreate(BaseModel):
    """
    Structured output model for creating reminders from user messages.

    This model is used with LLM structured output to extract reminder
    information from natural language user input.
    """

    message: str = Field(
        description="The reminder message text that will be sent to the user"
    )
    reminder_date: datetime = Field(
        description="The date and time when the reminder should be sent (ISO format)"
    )
    user_id: int = Field(
        description="Telegram user ID of the user creating the reminder"
    )
    timezone: str = Field(
        default="GMT+3",
        description="Timezone for the reminder. Always GMT+3.",
    )
    recurring: RecurringPattern = Field(
        default=RecurringPattern.NOT_SPECIFIED,
        description="Recurring pattern for the reminder. Use 'NOT SPECIFIED' if user doesn't specify recurrence.",
    )
    recurring_interval_minutes: Optional[int] = Field(
        default=None,
        description="For recurring='minutes' only: interval in minutes (e.g. 5, 15, 30). Required when recurring is 'minutes'.",
    )

    def get_recurring_pattern_for_db(self) -> str:
        """Return the recurring_pattern string for database storage."""
        if self.recurring == RecurringPattern.EVERY_MINUTES:
            n = self.recurring_interval_minutes or 15
            return f"minutes:{n}"
        return self.recurring.value

    def get_recurring_display_str(self) -> str:
        """Return human-readable recurring string for display."""
        if self.recurring == RecurringPattern.EVERY_MINUTES:
            n = self.recurring_interval_minutes or 15
            return f"каждые {n} мин"
        if self.recurring and self.recurring != RecurringPattern.NOT_SPECIFIED:
            return self.recurring.value
        return ""


class ReminderCreateList(BaseModel):
    """
    Structured output model for creating multiple reminders from user messages.

    This model is used with LLM structured output to extract multiple reminders
    from natural language user input.
    """

    reminders: List[ReminderCreate] = Field(
        description="List of reminders to create. Can contain one or more reminders.",
        min_length=1,
    )


def format_reminder_date_for_display(dt: datetime, tz_str: str = "GMT+3") -> str:
    """Convert reminder_date (stored in UTC) to user's timezone for display."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    offset_hours = 3
    if tz_str:
        tz_upper = tz_str.upper()
        if "+" in tz_upper:
            try:
                part = tz_upper.split("+")[1].strip().split(":")[0]
                offset_hours = int(part) if part else 3
            except (ValueError, IndexError):
                pass
        elif "-" in tz_upper and ("GMT" in tz_upper or "UTC" in tz_upper):
            try:
                part = tz_upper.split("-")[1].strip().split(":")[0]
                offset_hours = -int(part) if part else -3
            except (ValueError, IndexError):
                pass
    user_tz = timezone(timedelta(hours=offset_hours))
    local = dt.astimezone(user_tz)
    return local.strftime("%Y-%m-%d %H:%M")


def format_recurring_pattern_display(pattern: Optional[str]) -> str:
    """Format recurring_pattern string for human-readable display."""
    if not pattern or pattern.upper() == "NOT SPECIFIED":
        return ""
    p = pattern.lower()
    if p.startswith("minutes:"):
        try:
            n = int(p.split(":")[1])
            return f"каждые {n} мин"
        except (ValueError, IndexError):
            return pattern
    return pattern


class ReminderRecord(BaseModel):
    """
    Database record model for reminders.

    Represents a reminder as stored in the database.
    """

    id: UUID
    user_id: int
    message: str
    reminder_date: datetime
    timezone: str
    recurring_pattern: Optional[str]
    sent: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
