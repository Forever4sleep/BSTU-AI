"""
Scheduler Agent

Uses agent pattern with tools to extract reminder information
from user messages. The agent can use tools like get_current_date
to properly parse relative dates.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, List, Optional
from uuid import UUID

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from agents.scheduler.database import ReminderDatabaseService
from agents.scheduler.tools import calculate_date, get_current_date
from config.openrouter import (
    get_openrouter_api_key,
    get_openrouter_base_url,
    get_openrouter_model,
)
from shared.models.reminder import (
    RecurringPattern,
    ReminderCreate,
    ReminderCreateList,
    format_recurring_pattern_display,
    format_reminder_date_for_display,
)

logger = logging.getLogger(__name__)

# GMT+3 timezone
GMT3 = timezone(timedelta(hours=3))

REMINDER_EXTRACTION_SYSTEM_PROMPT = """Вы - агент для извлечения информации о напоминаниях в боте-помощнике студентов БГТУ.

Ваша задача - извлечь из сообщения пользователя информацию о напоминаниях и вернуть их в формате JSON.
Сообщение может содержать одно или несколько напоминаний. Если пользователь просит создать несколько напоминаний,
верните список всех напоминаний.

Формат ответа:
{{
    "reminders": [
        {{
            "message": "Текст напоминания",
            "reminder_date": "YYYY-MM-DDTHH:MM:SS+03:00",
            "timezone": "GMT+3",
            "recurring": "NOT SPECIFIED" | "daily" | "weekly" | "monthly" | "minutes",
            "recurring_interval_minutes": null или число (только при recurring="minutes")
        }}
    ]
}}

Правила:
- timezone всегда "GMT+3"
- recurring: "NOT SPECIFIED" если пользователь не указал периодичность
- recurring: "minutes" если пользователь сказал "каждые N минут" (напр. каждые 5 минут, каждые 15 минут)
- recurring_interval_minutes: число N при recurring="minutes" (обязательно)
- Если время не указано, используйте 9:00 утра
- reminder_date должен быть в формате ISO с timezone: YYYY-MM-DDTHH:MM:SS+03:00
- Если пользователь просит создать несколько напоминаний (например, "напомни мне в понедельник и вторник"),
  верните список с несколькими элементами
- Если пользователь просит создать одно напоминание, верните список с одним элементом
"""


class SchedulerAgent:
    """Agent that handles reminder creation from user messages."""

    def __init__(
        self,
        database_service: ReminderDatabaseService,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        """
        Initialize the scheduler agent.

        Args:
            database_service: ReminderDatabaseService instance
            api_key: OpenRouter API key (if None, will load from env)
            model: Model name (if None, will load from env)
            base_url: Base URL for API (if None, will use default OpenRouter URL)
        """
        self.database_service = database_service
        self.api_key = api_key or get_openrouter_api_key()
        self.model = model or get_openrouter_model()
        self.base_url = base_url or get_openrouter_base_url()

        # Initialize LLM
        llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0,
        )

        # Create tools
        tools = [get_current_date, calculate_date]

        # Create agent with structured output using ToolStrategy
        # This ensures the agent always returns ReminderCreateList schema (list of reminders)
        self.agent = create_agent(
            model=llm,
            tools=tools,
            response_format=ToolStrategy(ReminderCreateList),
        )
        self.system_prompt = REMINDER_EXTRACTION_SYSTEM_PROMPT

        logger.info(
            f"Initialized SchedulerAgent with model: {self.model}, "
            f"base_url: {self.base_url}"
        )

    async def extract_reminder_info(
        self, user_message: str, user_id: int
    ) -> List[ReminderCreate]:
        """
        Extract reminder information from user message using agent.

        Args:
            user_message: User's natural language message about creating reminders
            user_id: Telegram user ID

        Returns:
            List of ReminderCreate objects (NOT saved to database yet)

        Raises:
            ValueError: If extraction fails or returns invalid data
        """
        try:
            user_prompt = (
                f"Извлеките информацию о напоминаниях из следующего сообщения пользователя:\n\n"
                f"{user_message}\n\n"
                f"User ID: {user_id}\n\n"
                f"Верните финальный ответ в формате JSON с полем reminders (список напоминаний). "
                f"Каждое напоминание должно содержать поля: message, reminder_date, timezone, recurring."
            )

            logger.info("=" * 80)
            logger.info("📅 REMINDER EXTRACTION REQUEST (Agent)")
            logger.info("=" * 80)
            logger.info(f"📝 User Message: {user_message}")
            logger.info(f"👤 User ID: {user_id}")
            logger.info(f"🤖 Model: {self.model}")

            # Run agent with structured output
            # The agent will use tools and return structured_response
            result = await self.agent.ainvoke({
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            })

            logger.info("-" * 80)
            logger.info("📦 AGENT OUTPUT:")
            logger.info("-" * 80)
            logger.info(json.dumps(result, indent=2, ensure_ascii=False, default=str))

            # Extract structured response from agent
            # With ToolStrategy, the agent returns a structured_response field
            result_obj = result.get("structured_response")
            
            if not result_obj:
                raise ValueError(
                    f"No structured_response found in agent result: {result}"
                )
            
            # Validate the result
            if not isinstance(result_obj, ReminderCreateList):
                if isinstance(result_obj, dict):
                    result_obj = ReminderCreateList(**result_obj)
                else:
                    raise ValueError(f"Unexpected result type: {type(result_obj)}")
            
            # Extract reminders list
            reminders = result_obj.reminders
            
            # Ensure user_id and timezone are set correctly for all reminders
            for reminder in reminders:
                reminder.user_id = user_id
                reminder.timezone = "GMT+3"
                # Default recurring_interval_minutes for "every X minutes"
                if reminder.recurring == RecurringPattern.EVERY_MINUTES and not reminder.recurring_interval_minutes:
                    reminder.recurring_interval_minutes = 15
                # Ensure timezone-aware datetime
                if reminder.reminder_date.tzinfo is None:
                    reminder.reminder_date = reminder.reminder_date.replace(tzinfo=GMT3)

            # Log structured output
            logger.info("-" * 80)
            logger.info("📊 EXTRACTED REMINDERS DATA:")
            logger.info("-" * 80)
            logger.info(f"  Found {len(reminders)} reminder(s):")
            for idx, reminder in enumerate(reminders, 1):
                logger.info(f"  {idx}. Message: {reminder.message}")
                logger.info(f"     Date: {reminder.reminder_date}")
                logger.info(f"     Timezone: {reminder.timezone}")
                logger.info(
                    f"     Recurring: {reminder.recurring.value if reminder.recurring else 'None'}"
                )
            logger.info("=" * 80)

            return reminders

        except ValidationError as e:
            logger.error(f"Validation error in reminder extraction: {e}")
            raise ValueError(f"Invalid reminder extraction result: {e}") from e
        except Exception as e:
            logger.error(f"Error extracting reminder: {e}", exc_info=True)
            raise ValueError(f"Failed to extract reminder: {e}") from e

    async def create_reminder(
        self, reminder: ReminderCreate
    ) -> UUID:
        """
        Save reminder to database.

        Args:
            reminder: ReminderCreate object

        Returns:
            UUID of created reminder
        """
        reminder_id = await self.database_service.create_reminder(reminder)
        logger.info(f"Created reminder {reminder_id} in database")
        return reminder_id

    async def create_reminders(
        self, reminders: List[ReminderCreate]
    ) -> List[UUID]:
        """
        Save multiple reminders to database.

        Args:
            reminders: List of ReminderCreate objects

        Returns:
            List of UUIDs of created reminders
        """
        reminder_ids = await self.database_service.create_reminders(reminders)
        logger.info(f"Created {len(reminder_ids)} reminders in database")
        return reminder_ids

    def format_reminder_confirmation(
        self, reminders: List[ReminderCreate]
    ) -> str:
        """
        Format a confirmation message for the reminders (before saving).

        Args:
            reminders: List of ReminderCreate objects

        Returns:
            Formatted confirmation message
        """
        if len(reminders) == 1:
            reminder = reminders[0]
            date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
            recurring_str = ""
            if reminder.recurring and reminder.recurring.value != "NOT SPECIFIED":
                recurring_str = f" (повтор: {reminder.get_recurring_display_str()})"

            message = (
                f"📝 Сообщение: {reminder.message}\n"
                f"📅 Дата: {date_str} ({reminder.timezone}){recurring_str}\n\n"
                f"Подтвердите создание напоминания:"
            )
        else:
            message = f"📋 Создать {len(reminders)} напоминаний:\n\n"
            for idx, reminder in enumerate(reminders, 1):
                date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
                recurring_str = ""
                if reminder.recurring and reminder.recurring.value != "NOT SPECIFIED":
                    recurring_str = f" (повтор: {reminder.get_recurring_display_str()})"
                
                message += (
                    f"{idx}. 📝 {reminder.message}\n"
                    f"   📅 {date_str} ({reminder.timezone}){recurring_str}\n\n"
                )
            message += "Подтвердите создание напоминаний:"

        return message

    async def view_reminders(self, user_id: int, limit: int = 5) -> str:
        """
        View user's reminders.

        Args:
            user_id: Telegram user ID
            limit: Maximum number of reminders to show (default: 5)

        Returns:
            Formatted message with reminders list
        """
        reminders = await self.database_service.get_user_reminders(user_id, limit)

        if not reminders:
            return "📋 У вас пока нет напоминаний."

        message = f"📋 Ваши напоминания (показано до {limit}):\n\n"

        for idx, reminder in enumerate(reminders, 1):
            date_str = format_reminder_date_for_display(
                reminder.reminder_date, reminder.timezone
            )
            recurring_str = ""
            if reminder.recurring_pattern:
                recurring_str = f" (повтор: {format_recurring_pattern_display(reminder.recurring_pattern)})"

            message += (
                f"{idx}. 🔔 {reminder.message}\n"
                f"   📅 {date_str}{recurring_str}\n"
                f"   ID: {reminder.id}\n\n"
            )

        return message

