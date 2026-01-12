"""
Scheduler Agent

Helps students manage academic time and deadlines.
Fully natural-language driven with Telegram integration.

Supported Intents:
- schedule.lookup
- schedule.deadline.lookup
- schedule.reminder.create
"""

from agents.scheduler.agent import SchedulerAgent
from agents.scheduler.database import ReminderDatabaseService

__all__ = ["SchedulerAgent", "ReminderDatabaseService"]
