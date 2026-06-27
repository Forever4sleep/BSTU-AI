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
            RouterResponse if an agent handled the intent, None otherwise
        """
        # TODO: Route to Learning Agent and Academic Agent when implemented
        return None
