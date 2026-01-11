"""Base agent class."""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from src.schemas.agent import AgentRequest, AgentResponse


class BaseAgent(ABC):
    """Base class for all agents."""
    
    def __init__(self, name: str):
        """Initialize base agent."""
        self.name = name
    
    @abstractmethod
    async def process(self, request: AgentRequest) -> AgentResponse:
        """Process a request and return a response."""
        pass
    
    @abstractmethod
    def can_handle(self, intent: str) -> bool:
        """Check if this agent can handle a specific intent."""
        pass
    
    def validate_request(self, request: AgentRequest) -> bool:
        """Validate an agent request."""
        pass
