"""
Chat repository — database operations for ChatSession, Message, and AgentLog.

Session lifecycle:
  1. create_session()        — creates a new chat_sessions row
  2. create_user_message()   — saves the user's query to messages
  3. create_assistant_message() — saves the agent's final response
  4. create_agent_log()      — persists per-agent observability data
  5. update_session_activity() — bumps last_active_at and message_count

All methods take user_id and verify ownership before operating,
preventing horizontal privilege escalation.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import AgentLog, ChatSession, Message

logger = get_logger(__name__)


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Session ───────────────────────────────────────────────────────────────

    async def create_session(
        self,
        *,
        user_id: str,
        title: Optional[str] = None,
        document_ids: list[str],
        session_type: str = "chat",
    ) -> ChatSession:
        """Create a new chat session and return the ORM instance."""
        doc_uuids = [uuid.UUID(did) for did in document_ids]
        session_obj = ChatSession(
            user_id=uuid.UUID(user_id),
            title=title,
            document_ids=doc_uuids,
            session_type=session_type,
        )
        self._session.add(session_obj)
        await self._session.flush()
        await self._session.refresh(session_obj)
        logger.info(
            "session_created",
            session_id=str(session_obj.id),
            user_id=user_id,
        )
        return session_obj

    async def get_session(
        self,
        session_id: str,
        user_id: str,
    ) -> Optional[ChatSession]:
        """Load a session by ID, verifying user ownership."""
        stmt = select(ChatSession).where(
            ChatSession.id == uuid.UUID(session_id),
            ChatSession.user_id == uuid.UUID(user_id),
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        user_id: str,
        include_archived: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[ChatSession], int]:
        """Paginated list of sessions for a user, newest first."""
        filters = [ChatSession.user_id == uuid.UUID(user_id)]
        if not include_archived:
            filters.append(ChatSession.is_archived.is_(False))

        count_stmt = (
            select(func.count())
            .select_from(ChatSession)
            .where(*filters)
        )
        total: int = (await self._session.execute(count_stmt)).scalar_one()

        list_stmt = (
            select(ChatSession)
            .where(*filters)
            .order_by(ChatSession.last_active_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(list_stmt)
        sessions = list(result.scalars().all())
        return sessions, total

    async def update_session_activity(
        self,
        session_id: str,
        user_id: str,
        title: Optional[str] = None,
    ) -> None:
        """Bump last_active_at and increment message_count."""
        values: dict = {
            "last_active_at": datetime.now(tz=timezone.utc),
            "message_count": ChatSession.message_count + 2,  # user + assistant
        }
        if title is not None:
            values["title"] = title

        stmt = (
            update(ChatSession)
            .where(
                ChatSession.id == uuid.UUID(session_id),
                ChatSession.user_id == uuid.UUID(user_id),
            )
            .values(**values)
        )
        await self._session.execute(stmt)

    async def archive_session(self, session_id: str, user_id: str) -> bool:
        """Archive a session. Returns True if the session was found and updated."""
        stmt = (
            update(ChatSession)
            .where(
                ChatSession.id == uuid.UUID(session_id),
                ChatSession.user_id == uuid.UUID(user_id),
            )
            .values(is_archived=True)
            .returning(ChatSession.id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none() is not None

    # ── Messages ──────────────────────────────────────────────────────────────

    async def create_user_message(
        self,
        *,
        session_id: str,
        user_id: str,
        content: str,
        intent: Optional[str] = None,
    ) -> Message:
        """Persist the user's query."""
        msg = Message(
            session_id=uuid.UUID(session_id),
            user_id=uuid.UUID(user_id),
            role="user",
            content=content,
            intent=intent,
        )
        self._session.add(msg)
        await self._session.flush()
        await self._session.refresh(msg)
        return msg

    async def create_assistant_message(
        self,
        *,
        session_id: str,
        user_id: str,
        content: str,
        content_type: str = "text",
        intent: Optional[str] = None,
        structured_data: Optional[dict] = None,
        sources: Optional[list] = None,
        agent_path: Optional[list[str]] = None,
        latency_ms: Optional[int] = None,
        token_count: Optional[int] = None,
    ) -> Message:
        """Persist the agent's final response."""
        msg = Message(
            session_id=uuid.UUID(session_id),
            user_id=uuid.UUID(user_id),
            role="assistant",
            content=content,
            content_type=content_type,
            intent=intent,
            structured_data=structured_data,
            sources=sources,
            agent_path=agent_path,
            latency_ms=latency_ms,
            token_count=token_count,
        )
        self._session.add(msg)
        await self._session.flush()
        await self._session.refresh(msg)
        return msg

    async def list_messages(
        self,
        session_id: str,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Message], int]:
        """
        Paginated message history for a session.

        Verifies session ownership via a subquery to prevent horizontal escalation.
        """
        # Verify session belongs to this user first
        session_check = await self.get_session(session_id, user_id)
        if session_check is None:
            return [], 0

        count_stmt = (
            select(func.count())
            .select_from(Message)
            .where(Message.session_id == uuid.UUID(session_id))
        )
        total: int = (await self._session.execute(count_stmt)).scalar_one()

        list_stmt = (
            select(Message)
            .where(Message.session_id == uuid.UUID(session_id))
            .order_by(Message.created_at.asc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(list_stmt)
        return list(result.scalars().all()), total

    async def get_recent_messages(
        self,
        session_id: str,
        user_id: str,
        limit: int = 10,
    ) -> list[Message]:
        """
        Load the N most recent messages for conversation history injection.

        Ordered ascending (oldest first) so they read chronologically.
        """
        session_check = await self.get_session(session_id, user_id)
        if session_check is None:
            return []

        subquery = (
            select(Message)
            .where(Message.session_id == uuid.UUID(session_id))
            .order_by(Message.created_at.desc())
            .limit(limit)
            .subquery()
        )
        stmt = (
            select(Message)
            .join(subquery, Message.id == subquery.c.id)
            .order_by(Message.created_at.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ── Agent Logs ────────────────────────────────────────────────────────────

    async def create_agent_log(
        self,
        *,
        message_id: Optional[str],
        session_id: str,
        user_id: str,
        agent_name: str,
        status: str = "success",
        latency_ms: Optional[int] = None,
        token_input: Optional[int] = None,
        token_output: Optional[int] = None,
        input_snapshot: Optional[dict] = None,
        output_snapshot: Optional[dict] = None,
        error_message: Optional[str] = None,
    ) -> AgentLog:
        """Persist a single agent's execution record."""
        log = AgentLog(
            message_id=uuid.UUID(message_id) if message_id else None,
            session_id=uuid.UUID(session_id),
            user_id=uuid.UUID(user_id),
            agent_name=agent_name,
            status=status,
            latency_ms=latency_ms,
            token_input=token_input,
            token_output=token_output,
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
            error_message=error_message,
        )
        self._session.add(log)
        await self._session.flush()
        return log
