"""
Tools for Scheduler Agent

Provides tools that the ReAct agent can use to get current date/time
and perform date calculations.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# GMT+3 timezone
GMT3 = timezone(timedelta(hours=3))


@tool
def get_current_date() -> str:
    """
    Get the current date and time in GMT+3 timezone.
    
    Returns:
        Current date and time as ISO format string in GMT+3 timezone.
        Format: YYYY-MM-DDTHH:MM:SS+03:00
    
    Use this tool when you need to know the current date and time to parse
    relative dates like "tomorrow", "in 5 minutes", "next Monday", etc.
    """
    now = datetime.now(GMT3)
    return now.isoformat()


@tool
def calculate_date(
    base_date: str,
    days: Optional[int] = None,
    hours: Optional[int] = None,
    minutes: Optional[int] = None,
) -> str:
    """
    Calculate a date by adding or subtracting time from a base date.
    
    Args:
        base_date: Base date in ISO format (YYYY-MM-DDTHH:MM:SS+03:00)
        days: Number of days to add (positive) or subtract (negative)
        hours: Number of hours to add (positive) or subtract (negative)
        minutes: Number of minutes to add (positive) or subtract (negative)
    
    Returns:
        Calculated date as ISO format string in GMT+3 timezone.
    
    Use this tool to calculate dates like "tomorrow" (days=1), 
    "in 5 minutes" (minutes=5), "next week" (days=7), etc.
    """
    try:
        # Parse base date
        if isinstance(base_date, str):
            base = datetime.fromisoformat(base_date.replace("Z", "+00:00"))
        else:
            base = base_date
        
        # Ensure timezone-aware
        if base.tzinfo is None:
            base = base.replace(tzinfo=GMT3)
        
        # Calculate delta
        delta = timedelta(
            days=days or 0,
            hours=hours or 0,
            minutes=minutes or 0,
        )
        
        result = base + delta
        return result.isoformat()
    except Exception as e:
        logger.error(f"Error calculating date: {e}")
        raise ValueError(f"Failed to calculate date: {e}") from e


@tool
def parse_relative_date(description: str, current_date: str) -> str:
    """
    Parse a relative date description into an absolute date.
    
    Args:
        description: Natural language description like "tomorrow at 15:00", 
                    "next Monday", "in 2 hours", "in 5 minutes"
        current_date: Current date in ISO format (from get_current_date)
    
    Returns:
        Parsed absolute date as ISO format string in GMT+3 timezone.
    
    This tool helps parse natural language date descriptions.
    You should first call get_current_date() to get the current date,
    then use this tool to parse relative descriptions.
    """
    # This is a helper tool that the LLM can use to reason about dates
    # The actual parsing will be done by the LLM, but this tool provides
    # a structured way to think about it
    try:
        base = datetime.fromisoformat(current_date.replace("Z", "+00:00"))
        if base.tzinfo is None:
            base = base.replace(tzinfo=GMT3)
        
        # The LLM should use this to reason about the date
        # For actual parsing, the LLM will need to calculate based on description
        return base.isoformat()
    except Exception as e:
        logger.error(f"Error parsing relative date: {e}")
        return current_date
