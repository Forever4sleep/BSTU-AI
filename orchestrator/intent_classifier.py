"""
Intent Classifier

Uses ChatOpenAI with OpenRouter to classify user intents from messages
using structured output from LangChain.
"""

import json
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

            logger.info("=" * 80)
            logger.info("🔍 INTENT CLASSIFICATION REQUEST")
            logger.info("=" * 80)
            logger.info(f"📝 User Message: {message}")
            logger.info(f"🤖 Model: {self.model}")

            # Use structured output to get IntentClassification
            result = await self.llm.ainvoke(
                [
                    ("system", INTENT_CLASSIFICATION_SYSTEM_PROMPT),
                    ("user", user_prompt),
                ]
            )

            # Log raw JSON structured output
            logger.info("-" * 80)
            logger.info("📦 RAW JSON STRUCTURED OUTPUT:")
            logger.info("-" * 80)
            
            # Convert result to dict to show raw JSON structure
            if isinstance(result, IntentClassification):
                # Convert Pydantic model to dict
                raw_json = result.model_dump()
            elif isinstance(result, dict):
                raw_json = result
            else:
                # Try to convert to dict
                raw_json = dict(result) if hasattr(result, '__dict__') else str(result)
            
            logger.info(json.dumps(raw_json, indent=2, ensure_ascii=False))

            # Validate the result
            if not isinstance(result, IntentClassification):
                # If result is a dict, convert it
                if isinstance(result, dict):
                    result = IntentClassification(**result)
                else:
                    raise ValueError(f"Unexpected result type: {type(result)}")

            # Log structured output
            logger.info("-" * 80)
            logger.info("📊 STRUCTURED OUTPUT:")
            logger.info("-" * 80)
            
            # Log as JSON for readability
            output_dict = {
                "intents": result.intents,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
            }
            logger.info(json.dumps(output_dict, indent=2, ensure_ascii=False))
            
            # Log intents separately for clarity
            logger.info("-" * 80)
            logger.info("🎯 DETECTED INTENTS:")
            logger.info("-" * 80)
            if result.intents:
                for i, intent in enumerate(result.intents, 1):
                    logger.info(f"  {i}. {intent}")
            else:
                logger.info("  ❌ No intents detected")
            
            logger.info("-" * 80)
            logger.info(f"📈 Confidence: {result.confidence:.1%}")
            if result.reasoning:
                logger.info(f"💭 Reasoning: {result.reasoning}")
            logger.info("=" * 80)

            return result

        except ValidationError as e:
            logger.error(f"Validation error in intent classification: {e}")
            raise ValueError(f"Invalid intent classification result: {e}") from e
        except Exception as e:
            logger.error(f"Error classifying intent: {e}", exc_info=True)
            raise ValueError(f"Failed to classify intent: {e}") from e
