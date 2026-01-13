"""
Intent Router

Routes classified intents to appropriate agents.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from shared.intents.schemas import IntentClassification

logger = logging.getLogger(__name__)


@dataclass
class RouterResponse:
    """Response from router with optional confirmation data."""
    message: str
    needs_confirmation: bool = False
    confirmation_data: Optional[dict] = None
    show_reminder_menu: bool = False  # Show reminder selection menu


class IntentRouter:
    """Routes intents to appropriate agents."""

    def __init__(self, scheduler_agent: Optional[object] = None):
        """
        Initialize the intent router.

        Args:
            scheduler_agent: Optional SchedulerAgent instance
        """
        self.scheduler_agent = scheduler_agent

    async def route(
        self, classification: IntentClassification, user_message: str, user_id: int
    ) -> Optional[RouterResponse]:
        """
        Route intents to appropriate agents and return response.

        Args:
            classification: IntentClassification from intent classifier
            user_message: Original user message
            user_id: Telegram user ID

        Returns:
            RouterResponse with message and optional confirmation data, or None if no agent handled the intent
        """
        intents = classification.intents

        if not intents:
            return None

        # Route to scheduler agent for reminder operations
        if self.scheduler_agent:
            try:
                # Create reminder(s)
                if "schedule.reminder.create" in intents:
                    # Extract reminder info (don't save to DB yet)
                    reminders = await self.scheduler_agent.extract_reminder_info(
                        user_message, user_id
                    )
                    
                    # Format confirmation message
                    confirmation_message = (
                        self.scheduler_agent.format_reminder_confirmation(reminders)
                    )
                    
                    # Serialize reminders list for confirmation
                    reminders_json = [reminder.model_dump_json() for reminder in reminders]
                    
                    # Return response with confirmation data
                    return RouterResponse(
                        message=confirmation_message,
                        needs_confirmation=True,
                        confirmation_data={
                            "type": "reminder",
                            "reminders": reminders_json,
                        },
                    )

                # View reminders - show menu to select reminder
                elif "schedule.reminder.view" in intents:
                    reminders = await self.scheduler_agent.database_service.get_user_reminders(
                        user_id, limit=5
                    )
                    if not reminders:
                        return RouterResponse(
                            message="📋 У вас нет напоминаний."
                        )
                    return RouterResponse(
                        message="📋 Выберите напоминание:",
                        show_reminder_menu=True,
                        confirmation_data={"action": "view"},
                    )

                # Edit reminder - show menu to select reminder
                elif "schedule.reminder.edit" in intents:
                    reminders = await self.scheduler_agent.database_service.get_user_reminders(
                        user_id, limit=5
                    )
                    if not reminders:
                        return RouterResponse(
                            message="📋 У вас нет напоминаний для редактирования."
                        )
                    return RouterResponse(
                        message="📝 Выберите напоминание для редактирования:",
                        show_reminder_menu=True,
                        confirmation_data={"action": "edit"},
                    )

                # Delete reminder - show menu to select reminder
                elif "schedule.reminder.delete" in intents:
                    reminders = await self.scheduler_agent.database_service.get_user_reminders(
                        user_id, limit=5
                    )
                    if not reminders:
                        return RouterResponse(
                            message="📋 У вас нет напоминаний для удаления."
                        )
                    return RouterResponse(
                        message="🗑️ Выберите напоминание для удаления:",
                        show_reminder_menu=True,
                        confirmation_data={"action": "delete"},
                    )

            except Exception as e:
                logger.error(f"Error routing to scheduler agent: {e}", exc_info=True)
                return RouterResponse(
                    message=(
                        "❌ Произошла ошибка при обработке запроса. "
                        "Попробуйте еще раз."
                    )
                )

        # TODO: Route to other agents as they are implemented
        # if "learning.explain" in intents:
        #     return await self.learning_agent.explain(...)
        # if "academic.professor.profile" in intents:
        #     return await self.academic_agent.get_professor_profile(...)

        return None
