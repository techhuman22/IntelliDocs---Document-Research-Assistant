"""
Chat service — orchestrates the LangGraph pipeline and persists results.

Responsibilities:
  1. Create or load a ChatSession.
  2. Load conversation history from the DB for multi-turn context.
  3. Convert DB messages to LangChain BaseMessage objects.
  4. Build the initial AgentState.
  5. Inject per-request services into the LangGraph config.
  6. Invoke the workflow (ainvoke for regular, astream for streaming).
  7. Persist the user message, assistant message, and all agent logs to DB.
  8. Return a ChatResponse schema object.

Session auto-title:
  If no title is provided, the service generates one from the first 60 chars
  of the user's query. This is stored when updating session activity.

Streaming architecture (Task 12):
  chat_service.stream() is an async generator that yields StreamEvent objects.

  Under the hood, LangGraph's .astream() yields one dict per completed node.
  We yield:
    StreamEvent(event_type="agent_start", data={"agent": "router"})
    StreamEvent(event_type="agent_end",   data={"agent": "router", "latency_ms": 45})
    ...
    StreamEvent(event_type="final",       data=<full ChatResponse dict>)

  The FastAPI endpoint wraps this in a StreamingResponse using JSON Lines
  (one JSON object per line, newline-delimited), which is compatible with
  standard HTTP clients and EventSource.

  Token-level streaming (individual LLM tokens) is NOT implemented here
  because Gemini's streaming API is per-chunk, not per-token, and the
  structured output (quiz/summary) cannot be streamed partially.
  The architecture is designed for node-level streaming: the UI can show
  "Analyzing query..." → "Retrieving documents..." → "Generating answer..."
  which is the right UX for a research assistant.
"""

import json
import time
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState, initial_state
from app.agents.workflow import workflow_app
from app.core.exceptions import NotFoundException, SessionNotFoundException
from app.core.logging import get_logger
from app.db.repositories.chat_repository import ChatRepository
from app.db.repositories.document_repository import DocumentRepository
from app.schemas.chat import (
    AgentTraceEntry,
    ChatResponse,
    CitationResponse,
    StreamEvent,
)
from app.services.context_builder_service import ContextBuilderService
from app.services.embedding_service import EmbeddingService
from app.services.retrieval_service import RetrievalService

logger = get_logger(__name__)

_HISTORY_MESSAGE_LIMIT = 10  # load last 10 messages for multi-turn context


class ChatService:
    """
    Orchestrates the full query → agents → response → persistence pipeline.

    Instantiated per-request by the FastAPI dependency.
    """

    def __init__(
        self,
        session: AsyncSession,
        retrieval_service: RetrievalService,
    ) -> None:
        self._session = session
        self._chat_repo = ChatRepository(session)
        self._doc_repo = DocumentRepository(session)
        self._retrieval_service = retrieval_service
        self._context_builder = ContextBuilderService()

    # ── Public: regular (non-streaming) ──────────────────────────────────────

    async def chat(
        self,
        *,
        query: str,
        user_id: str,
        session_id: Optional[str] = None,
        document_ids: list[str],
    ) -> ChatResponse:
        """
        Process a user query through the multi-agent pipeline.

        Creates a new session if session_id is None.
        Returns a fully-populated ChatResponse.
        """
        t_start = time.perf_counter()

        # ── 1. Session setup ──────────────────────────────────────────────────
        chat_session = await self._get_or_create_session(
            user_id=user_id,
            session_id=session_id,
            document_ids=document_ids,
        )
        sid = str(chat_session.id)

        # ── 2. Load conversation history ──────────────────────────────────────
        history_messages = await self._load_history(sid, user_id)

        # ── 3. Build initial state ────────────────────────────────────────────
        state = initial_state(
            user_id=user_id,
            session_id=sid,
            query=query,
            document_ids=document_ids,
            history_messages=history_messages,
        )

        # ── 4. Run LangGraph workflow ─────────────────────────────────────────
        config = self._build_config(sid)
        final_state: AgentState = await workflow_app.ainvoke(state, config=config)

        total_ms = int((time.perf_counter() - t_start) * 1000)

        # ── 5. Persist messages ───────────────────────────────────────────────
        auto_title = None
        if chat_session.message_count == 0:
            auto_title = query[:60] + ("..." if len(query) > 60 else "")

        user_msg = await self._chat_repo.create_user_message(
            session_id=sid,
            user_id=user_id,
            content=query,
            intent=final_state.get("intent"),
        )

        intent = final_state.get("intent", "qa")
        structured_data = final_state.get("summary") or final_state.get("quiz")
        content_type = "text" if intent == "qa" else intent  # "summary" | "quiz"
        citations = self._build_citations(final_state)
        agent_path = [t["agent_name"] for t in final_state.get("agent_trace", [])]

        assistant_msg = await self._chat_repo.create_assistant_message(
            session_id=sid,
            user_id=user_id,
            content=final_state.get("final_response", ""),
            content_type=content_type,
            intent=intent,
            structured_data=structured_data,
            sources=[c.model_dump() for c in citations],
            agent_path=agent_path,
            latency_ms=total_ms,
        )

        # ── 6. Persist agent logs ─────────────────────────────────────────────
        await self._persist_agent_logs(
            trace=final_state.get("agent_trace", []),
            message_id=str(assistant_msg.id),
            session_id=sid,
            user_id=user_id,
        )

        # ── 7. Update session activity ────────────────────────────────────────
        await self._chat_repo.update_session_activity(
            session_id=sid,
            user_id=user_id,
            title=auto_title,
        )

        await self._session.commit()

        # ── 8. Build response ─────────────────────────────────────────────────
        return ChatResponse(
            session_id=chat_session.id,
            message_id=assistant_msg.id,
            query=query,
            intent=intent,
            response=final_state.get("final_response", ""),
            structured_data=structured_data,
            citations=citations,
            agent_trace=[AgentTraceEntry(**t) for t in final_state.get("agent_trace", [])],
            latency_ms=total_ms,
        )

    # ── Public: streaming ─────────────────────────────────────────────────────

    async def stream(
        self,
        *,
        query: str,
        user_id: str,
        session_id: Optional[str] = None,
        document_ids: list[str],
    ) -> AsyncGenerator[StreamEvent, None]:
        """
        Stream agent progress events and the final response.

        Yields StreamEvent objects in this sequence:
          agent_start  (for each node as it begins)
          agent_end    (for each node as it completes)
          final        (the complete ChatResponse as the last event)
          error        (if something goes wrong)

        The caller (FastAPI endpoint) serializes these to JSON Lines:
          data: {"event_type": "agent_start", "data": {...}}\\n\\n

        Usage:
          async for event in chat_service.stream(...):
              yield f"data: {event.model_dump_json()}\\n\\n"
        """
        t_start = time.perf_counter()

        try:
            chat_session = await self._get_or_create_session(
                user_id=user_id,
                session_id=session_id,
                document_ids=document_ids,
            )
            sid = str(chat_session.id)
            history_messages = await self._load_history(sid, user_id)
            state = initial_state(
                user_id=user_id,
                session_id=sid,
                query=query,
                document_ids=document_ids,
                history_messages=history_messages,
            )
            config = self._build_config(sid)
            final_state: Optional[AgentState] = None

            # Stream node-by-node events
            async for event_dict in workflow_app.astream(state, config=config):
                # event_dict: {"node_name": {state_updates}}
                for node_name, node_output in event_dict.items():
                    trace = node_output.get("agent_trace", [])
                    if trace:
                        latest = trace[-1]
                        yield StreamEvent(
                            event_type="agent_end",
                            data={
                                "agent": node_name,
                                "status": latest.get("status"),
                                "latency_ms": latest.get("latency_ms"),
                            },
                        )
                    else:
                        yield StreamEvent(
                            event_type="agent_start",
                            data={"agent": node_name},
                        )
                    # Keep track of the last state update as our final state
                    final_state = node_output

            # Merge full final state by re-invoking (stream only gives partial updates)
            # For correctness, we do a second ainvoke to get the complete final state
            # (alternatively, accumulate state manually in the stream loop)
            complete_state: AgentState = await workflow_app.ainvoke(state, config=config)
            total_ms = int((time.perf_counter() - t_start) * 1000)

            # Persist and build response
            response = await self._persist_and_build_response(
                query=query,
                user_id=user_id,
                chat_session=chat_session,
                final_state=complete_state,
                total_ms=total_ms,
            )

            yield StreamEvent(event_type="final", data=response.model_dump())

        except Exception as exc:
            logger.error("chat_stream_error", error=str(exc), exc_info=True)
            yield StreamEvent(
                event_type="error",
                data={"error": str(exc), "query": query},
            )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _get_or_create_session(
        self,
        *,
        user_id: str,
        session_id: Optional[str],
        document_ids: list[str],
    ):
        """Load existing session or create a new one."""
        if session_id:
            session_obj = await self._chat_repo.get_session(session_id, user_id)
            if session_obj is None:
                raise SessionNotFoundException(session_id)
            return session_obj

        # Auto-create new session
        session_obj = await self._chat_repo.create_session(
            user_id=user_id,
            document_ids=document_ids,
            session_type="chat",
        )
        await self._session.flush()
        return session_obj

    async def _load_history(
        self,
        session_id: str,
        user_id: str,
    ) -> list[BaseMessage]:
        """Load recent DB messages and convert to LangChain BaseMessage objects."""
        db_messages = await self._chat_repo.get_recent_messages(
            session_id=session_id,
            user_id=user_id,
            limit=_HISTORY_MESSAGE_LIMIT,
        )
        result: list[BaseMessage] = []
        for msg in db_messages:
            if msg.role == "user":
                result.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                result.append(AIMessage(content=msg.content))
        return result

    def _build_config(self, session_id: str) -> dict:
        """Build the LangGraph RunnableConfig with injected services."""
        return {
            "configurable": {
                "retrieval_service": self._retrieval_service,
                "context_builder": self._context_builder,
            },
            "run_name": f"agentflow-{session_id[:8]}",
            "tags": ["agentflow", "multi-agent"],
        }

    def _build_citations(self, final_state: AgentState) -> list[CitationResponse]:
        """Extract citations from retrieved chunks."""
        citations = []
        for i, chunk in enumerate(final_state.get("retrieved_chunks", []), start=1):
            citations.append(
                CitationResponse(
                    position=i,
                    document_id=chunk.document_id,
                    original_filename=chunk.original_filename,
                    page_number=chunk.page_number,
                    chunk_index=chunk.chunk_index,
                    similarity_score=chunk.similarity_score,
                )
            )
        return citations

    async def _persist_agent_logs(
        self,
        trace: list[dict],
        message_id: str,
        session_id: str,
        user_id: str,
    ) -> None:
        """Write one AgentLog row per entry in the agent_trace list."""
        for entry in trace:
            await self._chat_repo.create_agent_log(
                message_id=message_id,
                session_id=session_id,
                user_id=user_id,
                agent_name=entry.get("agent_name", "unknown"),
                status=entry.get("status", "success"),
                latency_ms=entry.get("latency_ms"),
                token_input=entry.get("token_input"),
                token_output=entry.get("token_output"),
            )

    async def _persist_and_build_response(
        self,
        *,
        query: str,
        user_id: str,
        chat_session,
        final_state: AgentState,
        total_ms: int,
    ) -> ChatResponse:
        """Shared persistence logic used by both chat() and stream()."""
        sid = str(chat_session.id)
        intent = final_state.get("intent", "qa")
        structured_data = final_state.get("summary") or final_state.get("quiz")
        citations = self._build_citations(final_state)
        agent_path = [t["agent_name"] for t in final_state.get("agent_trace", [])]

        user_msg = await self._chat_repo.create_user_message(
            session_id=sid,
            user_id=user_id,
            content=query,
            intent=intent,
        )
        assistant_msg = await self._chat_repo.create_assistant_message(
            session_id=sid,
            user_id=user_id,
            content=final_state.get("final_response", ""),
            content_type="text" if intent == "qa" else intent,
            intent=intent,
            structured_data=structured_data,
            sources=[c.model_dump() for c in citations],
            agent_path=agent_path,
            latency_ms=total_ms,
        )
        await self._persist_agent_logs(
            trace=final_state.get("agent_trace", []),
            message_id=str(assistant_msg.id),
            session_id=sid,
            user_id=user_id,
        )

        auto_title = None
        if chat_session.message_count == 0:
            auto_title = query[:60] + ("..." if len(query) > 60 else "")
        await self._chat_repo.update_session_activity(sid, user_id, title=auto_title)
        await self._session.commit()

        return ChatResponse(
            session_id=chat_session.id,
            message_id=assistant_msg.id,
            query=query,
            intent=intent,
            response=final_state.get("final_response", ""),
            structured_data=structured_data,
            citations=citations,
            agent_trace=[AgentTraceEntry(**t) for t in final_state.get("agent_trace", [])],
            latency_ms=total_ms,
        )
