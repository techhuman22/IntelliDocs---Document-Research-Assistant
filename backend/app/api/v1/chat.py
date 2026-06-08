"""
Chat API routes.

  POST   /chat                         — send a query, get full response
  POST   /chat/stream                  — send a query, get streaming events
  POST   /sessions                     — create a new chat session
  GET    /sessions                     — list sessions
  GET    /sessions/{session_id}        — get a single session
  DELETE /sessions/{session_id}        — archive a session
  GET    /sessions/{session_id}/messages — paginated message history

Route ordering:
  /sessions (collection) is declared before /sessions/{id} (item)
  to prevent FastAPI routing "sessions" as a UUID path parameter.

Streaming:
  POST /chat/stream returns a StreamingResponse with Content-Type text/event-stream.
  Each line is a JSON object followed by \\n\\n (standard SSE format).

  Client usage (JavaScript):
    const evtSource = new EventSource("/api/v1/chat/stream?...");
    // or use fetch with ReadableStream for POST with body

  The stream ends with an event_type="final" payload containing the full response.
"""

import json
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_chat_service,
    get_current_active_user,
    get_db,
)
from app.core.exceptions import SessionNotFoundException
from app.core.logging import get_logger
from app.db.models import User
from app.db.repositories.chat_repository import ChatRepository
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    MessageHistoryResponse,
    MessageResponse,
    SessionCreateRequest,
    SessionListResponse,
    SessionResponse,
)
from app.services.chat_service import ChatService

logger = get_logger(__name__)

router = APIRouter()


# ── Chat endpoints ────────────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Send a query to the multi-agent pipeline",
    description=(
        "Routes the query through Router → Retrieval → (Summary|Quiz)? → FinalResponse agents. "
        "Returns the complete response after all agents finish."
    ),
)
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> ChatResponse:
    """
    Process a user query through the LangGraph multi-agent pipeline.

    - Creates a new session if session_id is not provided.
    - Continues an existing session if session_id is provided.
    - Scopes retrieval to document_ids if provided; otherwise searches all user documents.
    """
    return await chat_service.chat(
        query=request.query,
        user_id=str(current_user.id),
        session_id=str(request.session_id) if request.session_id else None,
        document_ids=[str(did) for did in request.document_ids],
    )


@router.post(
    "/chat/stream",
    summary="Stream agent progress and final response",
    description=(
        "Returns a Server-Sent Events stream. "
        "Yields agent_start/agent_end events as each agent runs, "
        "then a final event with the complete response."
    ),
)
async def chat_stream(
    request: ChatRequest,
    current_user: User = Depends(get_current_active_user),
    chat_service: ChatService = Depends(get_chat_service),
) -> StreamingResponse:
    """
    Stream the multi-agent pipeline.

    Each event is a JSON object followed by double newline:
      data: {"event_type": "agent_end", "data": {"agent": "router", "latency_ms": 42}}\\n\\n
      data: {"event_type": "final",     "data": {...full ChatResponse...}}\\n\\n

    The stream is complete when the client receives the "final" event.
    """

    async def event_generator():
        async for event in chat_service.stream(
            query=request.query,
            user_id=str(current_user.id),
            session_id=str(request.session_id) if request.session_id else None,
            document_ids=[str(did) for did in request.document_ids],
        ):
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering for SSE
        },
    )


# ── Session endpoints ─────────────────────────────────────────────────────────

@router.post(
    "/sessions",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new chat session",
)
async def create_session(
    request: SessionCreateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Create a new chat session explicitly (before sending the first query)."""
    repo = ChatRepository(db)
    session_obj = await repo.create_session(
        user_id=str(current_user.id),
        title=request.title,
        document_ids=[str(did) for did in request.document_ids],
        session_type=request.session_type,
    )
    await db.commit()
    return SessionResponse.model_validate(session_obj)


@router.get(
    "/sessions",
    response_model=SessionListResponse,
    summary="List chat sessions",
)
async def list_sessions(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SessionListResponse:
    """List the authenticated user's chat sessions, newest first."""
    repo = ChatRepository(db)
    offset = (page - 1) * limit
    sessions, total = await repo.list_sessions(
        user_id=str(current_user.id),
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return SessionListResponse(
        sessions=[SessionResponse.model_validate(s) for s in sessions],
        total=total,
        page=page,
        limit=limit,
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionResponse,
    summary="Get a chat session",
)
async def get_session(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SessionResponse:
    """Get a single session by ID. Returns 404 if not found or not owned by user."""
    repo = ChatRepository(db)
    session_obj = await repo.get_session(str(session_id), str(current_user.id))
    if session_obj is None:
        raise SessionNotFoundException(str(session_id))
    return SessionResponse.model_validate(session_obj)


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Archive a chat session",
)
async def archive_session(
    session_id: UUID,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """
    Archive (soft-delete) a session.
    Archived sessions are excluded from the list by default.
    """
    repo = ChatRepository(db)
    found = await repo.archive_session(str(session_id), str(current_user.id))
    if not found:
        raise SessionNotFoundException(str(session_id))
    await db.commit()


@router.get(
    "/sessions/{session_id}/messages",
    response_model=MessageHistoryResponse,
    summary="Get message history for a session",
)
async def get_session_messages(
    session_id: UUID,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageHistoryResponse:
    """Paginated message history for a session. Ordered oldest to newest."""
    repo = ChatRepository(db)
    offset = (page - 1) * limit
    messages, total = await repo.list_messages(
        session_id=str(session_id),
        user_id=str(current_user.id),
        limit=limit,
        offset=offset,
    )
    if total == 0:
        # Either session not found or no messages — distinguish via session lookup
        session_obj = await repo.get_session(str(session_id), str(current_user.id))
        if session_obj is None:
            raise SessionNotFoundException(str(session_id))

    return MessageHistoryResponse(
        session_id=session_id,
        messages=[MessageResponse.model_validate(m) for m in messages],
        total=total,
        page=page,
        limit=limit,
    )
