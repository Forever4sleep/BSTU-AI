"""
Intent Classifier

Uses ChatOpenAI with OpenRouter to classify user intents from messages
using structured output from LangChain.
"""

import logging

from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from config.openrouter import (
    get_openrouter_api_key,
    get_openrouter_base_url,
    get_openrouter_model,
)
from orchestrator.prompts import INTENT_CLASSIFICATION_SYSTEM_PROMPT
from shared.intents.schemas import IntentClassification

logger = logging.getLogger(__name__)


class IntentClassifier:
    """Classifies user messages into intents using LLM with structured output."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
    ):
        """
        Initialize the intent classifier.

        Args:
            api_key: OpenRouter API key (if None, will load from env)
            model: Model name (if None, will load from env)
            base_url: Base URL for API (if None, will use default OpenRouter URL)
        """
        self.api_key = api_key or get_openrouter_api_key()
        self.model = model or get_openrouter_model()
        self.base_url = base_url or get_openrouter_base_url()

        # Initialize ChatOpenAI with structured output
        self.llm = ChatOpenAI(
            model=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
            temperature=0,  # Lower temperature for more consistent classification
        ).with_structured_output(IntentClassification)

        logger.info(
            f"Initialized IntentClassifier with model: {self.model}, "
            f"base_url: {self.base_url}"
        )

    async def classify(self, message: str) -> IntentClassification:
        """
        Classify intents from a user message.

        Args:
            message: User's message text

        Returns:
            IntentClassification object with detected intents

        Raises:
            ValueError: If classification fails or returns invalid data
        """
        try:
            user_prompt = f"Classify the following user message:\n\n{message}"

            # Use structured output to get IntentClassification
            result = await self.llm.ainvoke(
                [
                    ("system", INTENT_CLASSIFICATION_SYSTEM_PROMPT),
                    ("user", user_prompt),
                ]
            )

            # Validate the result
            if not isinstance(result, IntentClassification):
                # If result is a dict, convert it
                if isinstance(result, dict):
                    result = IntentClassification(**result)
                else:
                    raise ValueError(f"Unexpected result type: {type(result)}")

            logger.info(
                f"Classified message: '{message[:50]}...' -> "
                f"Intents: {result.intents}, Confidence: {result.confidence}"
            )

            return result

        except ValidationError as e:
            logger.error(f"Validation error in intent classification: {e}")
            raise ValueError(f"Invalid intent classification result: {e}") from e
        except Exception as e:
            logger.error(f"Error classifying intent: {e}", exc_info=True)
            raise ValueError(f"Failed to classify intent: {e}") from e
