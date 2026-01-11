"""
Intent Definitions

Contains intent classification and definitions used by the orchestrator
to route user requests to appropriate agents.
"""

from shared.intents.schemas import (
    AcademicIntent,
    IntentClassification,
    LearningIntent,
    ScheduleIntent,
)

__all__ = [
    "IntentClassification",
    "LearningIntent",
    "AcademicIntent",
    "ScheduleIntent",
]
