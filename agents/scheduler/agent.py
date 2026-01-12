"""
Scheduler Agent

Uses agent pattern with tools to extract reminder information
from user messages. The agent can use tools like get_current_date
to properly parse relative dates.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
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
from shared.models.reminder import ReminderCreate

logger = logging.getLogger(__name__)

# GMT+3 timezone
GMT3 = timezone(timedelta(hours=3))

REMINDER_EXTRACTION_SYSTEM_PROMPT = """Вы - агент для извлечения информации о напоминаниях в боте-помощнике студентов БГТУ.

Ваша задача - извлечь из сообщения пользователя информацию о напоминании и вернуть её в формате JSON:
{{
    "message": "Текст напоминания",
    "reminder_date": "YYYY-MM-DDTHH:MM:SS+03:00",
    "timezone": "GMT+3",
    "recurring": "NOT SPECIFIED" | "daily" | "weekly" | "monthly"
}}

Правила:
- timezone всегда "GMT+3"
- recurring: "NOT SPECIFIED" если пользователь не указал периодичность
- Если время не указано, используйте 9:00 утра
- reminder_date должен быть в формате ISO с timezone: YYYY-MM-DDTHH:MM:SS+03:00
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
        # This ensures the agent always returns ReminderCreate schema
        self.agent = create_agent(
            model=llm,
            tools=tools,
            response_format=ToolStrategy(ReminderCreate),
        )
        self.system_prompt = REMINDER_EXTRACTION_SYSTEM_PROMPT

        logger.info(
            f"Initialized SchedulerAgent with model: {self.model}, "
            f"base_url: {self.base_url}"
        )

    async def extract_reminder_info(
        self, user_message: str, user_id: int
    ) -> ReminderCreate:
        """
        Extract reminder information from user message using agent.

        Args:
            user_message: User's natural language message about creating a reminder
            user_id: Telegram user ID

        Returns:
            ReminderCreate object (NOT saved to database yet)

        Raises:
            ValueError: If extraction fails or returns invalid data
        """
        try:
            user_prompt = (
                f"Извлеките информацию о напоминании из следующего сообщения пользователя:\n\n"
                f"{user_message}\n\n"
                f"User ID: {user_id}\n\n"
                f"Верните финальный ответ в формате JSON с полями: message, reminder_date, timezone, recurring."
            )

            logger.info("=" * 80)
            logger.info("📅 REMINDER EXTRACTION REQUEST (ReAct Agent)")
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
            if not isinstance(result_obj, ReminderCreate):
                if isinstance(result_obj, dict):
                    result_obj = ReminderCreate(**result_obj)
                else:
                    raise ValueError(f"Unexpected result type: {type(result_obj)}")
            
            # Ensure user_id is set correctly
            result_obj.user_id = user_id

            # Ensure timezone is GMT+3
            result_obj.timezone = "GMT+3"

            # Ensure timezone-aware datetime
            if result_obj.reminder_date.tzinfo is None:
                result_obj.reminder_date = result_obj.reminder_date.replace(tzinfo=GMT3)

            # Log structured output
            logger.info("-" * 80)
            logger.info("📊 EXTRACTED REMINDER DATA:")
            logger.info("-" * 80)
            logger.info(f"  Message: {result_obj.message}")
            logger.info(f"  Date: {result_obj.reminder_date}")
            logger.info(f"  Timezone: {result_obj.timezone}")
            logger.info(
                f"  Recurring: {result_obj.recurring.value if result_obj.recurring else 'None'}"
            )
            logger.info("=" * 80)

            return result_obj

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

    def format_reminder_confirmation(
        self, reminder: ReminderCreate
    ) -> str:
        """
        Format a confirmation message for the reminder (before saving).

        Args:
            reminder: ReminderCreate object

        Returns:
            Formatted confirmation message
        """
        date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
        recurring_str = ""
        if reminder.recurring and reminder.recurring.value != "NOT SPECIFIED":
            recurring_str = f" (recurring: {reminder.recurring.value})"

        message = (
            f"📝 Сообщение: {reminder.message}\n"
            f"📅 Дата: {date_str} ({reminder.timezone}){recurring_str}\n\n"
            f"Подтвердите создание напоминания:"
        )

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
            date_str = reminder.reminder_date.strftime("%Y-%m-%d %H:%M")
            recurring_str = ""
            if reminder.recurring_pattern:
                recurring_str = f" (повтор: {reminder.recurring_pattern})"

            message += (
                f"{idx}. 🔔 {reminder.message}\n"
                f"   📅 {date_str}{recurring_str}\n"
                f"   ID: {reminder.id}\n\n"
            )

        return message

