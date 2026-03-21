"""Conversation persistence."""

import hashlib
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services.ingestion_service.db.models import Conversation, Message

logger = logging.getLogger(__name__)
THREAD_ID_HASH_LENGTH = 16


def _stringify_content(content: Any) -> str:
    """Normalize message content to a stable string representation."""
    return str(content)


def derive_thread_id(messages: list[dict[str, Any]]) -> str:
    """
    Stable fingerprint from the first user message.

    Open WebUI doesn't send a thread ID, so we hash the first
    user message content to group turns in the same conversation.
    """
    for message in messages:
        if message.get("role") == "user":
            content = _stringify_content(message.get("content", ""))
            return hashlib.sha256(content.encode()).hexdigest()[:THREAD_ID_HASH_LENGTH]
    return hashlib.sha256(str(messages).encode()).hexdigest()[:THREAD_ID_HASH_LENGTH]


class ConversationRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]):
        self._session_factory = session_factory

    async def save_turn(
        self,
        thread_id: str,
        user_messages: list[dict[str, Any]],
        assistant_content: str,
    ) -> None:
        """Upsert conversation and append new messages."""
        async with self._session_factory() as session:
            async with session.begin():
                stmt = select(Conversation).where(Conversation.thread_id == thread_id)
                result = await session.execute(stmt)
                conv = result.scalar_one_or_none()

                if conv is None:
                    conv = Conversation(thread_id=thread_id)
                    session.add(conv)
                    await session.flush()
                    next_ordinal = 0
                else:
                    last_ordinal_stmt = select(Message.ordinal).where(
                        Message.conversation_id == conv.id
                    ).order_by(Message.ordinal.desc()).limit(1)
                    last = await session.execute(last_ordinal_stmt)
                    row = last.scalar_one_or_none()
                    next_ordinal = (row + 1) if row is not None else 0

                for message in user_messages:
                    role = message.get("role", "user")
                    content = _stringify_content(message.get("content", ""))
                    session.add(
                        Message(
                            conversation_id=conv.id,
                            role=role,
                            content=content,
                            ordinal=next_ordinal,
                        )
                    )
                    next_ordinal += 1

                session.add(
                    Message(
                        conversation_id=conv.id,
                        role="assistant",
                        content=assistant_content,
                        ordinal=next_ordinal,
                    )
                )

        logger.debug("Saved turn for thread %s (ordinal up to %d)", thread_id, next_ordinal)
