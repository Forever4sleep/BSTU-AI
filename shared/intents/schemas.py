"""
Intent schemas for structured output classification.

Defines Pydantic models for intent classification that will be used
with LangChain's structured output functionality.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class LearningIntent(str, Enum):
    """Learning-related intents."""
    EXPLAIN = "learning.explain"
    SUMMARIZE = "learning.summarize"
    QUIZ_GENERATE = "learning.quiz.generate"
    QUIZ_GRADE = "learning.quiz.grade"
    PLAN_REVISION = "learning.plan.revision"


class AcademicIntent(str, Enum):
    """Academic-related intents."""
    PROFESSOR_PROFILE = "academic.professor.profile"
    COURSE_REQUIREMENTS = "academic.course.requirements"


class ScheduleIntent(str, Enum):
    """Schedule-related intents."""
    LOOKUP = "schedule.lookup"
    DEADLINE_LOOKUP = "schedule.deadline.lookup"
    REMINDER_CREATE = "schedule.reminder.create"
    REMINDER_EDIT = "schedule.reminder.edit"
    REMINDER_DELETE = "schedule.reminder.delete"
    REMINDER_LIST = "schedule.reminder.list"
    REMINDER_VIEW = "schedule.reminder.view"


class IntentClassification(BaseModel):
    """
    Structured output for intent classification.
    
    A single message can have multiple intents detected.
    """
    
    intents: List[str] = Field(
        description="List of detected intents from the user's message. "
        "Possible intents: learning.explain, learning.summarize, learning.quiz.generate, "
        "learning.quiz.grade, learning.plan.revision, academic.professor.profile, "
        "academic.course.requirements, schedule.lookup, schedule.deadline.lookup, "
        "schedule.reminder.create. Return an empty list if no intents are detected."
    )
    
    confidence: float = Field(
        description="Overall confidence score for the intent classification (0.0 to 1.0)",
        ge=0.0,
        le=1.0
    )
    
    reasoning: Optional[str] = Field(
        default=None,
        description="Brief explanation of why these intents were detected"
    )
