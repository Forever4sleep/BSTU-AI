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

        # Route to scheduler agent for reminder creation
        if "schedule.reminder.create" in intents and self.scheduler_agent:
            try:
                # Extract reminder info (don't save to DB yet)
                reminder = await self.scheduler_agent.extract_reminder_info(
                    user_message, user_id
                )
                
                # Format confirmation message
                confirmation_message = self.scheduler_agent.format_reminder_confirmation(
                    reminder
                )
                
                # Return response with confirmation data
                return RouterResponse(
                    message=confirmation_message,
                    needs_confirmation=True,
                    confirmation_data={
                        "type": "reminder",
                        "reminder": reminder.model_dump_json(),
                    },
                )
            except Exception as e:
                logger.error(f"Error routing to scheduler agent: {e}", exc_info=True)
                return RouterResponse(
                    message=(
                        "❌ Произошла ошибка при создании напоминания. "
                        "Попробуйте еще раз."
                    )
                )

        # TODO: Route to other agents as they are implemented
        # if "learning.explain" in intents:
        #     return await self.learning_agent.explain(...)
        # if "academic.professor.profile" in intents:
        #     return await self.academic_agent.get_professor_profile(...)

        return None
