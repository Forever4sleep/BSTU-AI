"""
Reminder Models

Pydantic models for reminder structured output and data representation.
"""

from datetime import datetime
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
