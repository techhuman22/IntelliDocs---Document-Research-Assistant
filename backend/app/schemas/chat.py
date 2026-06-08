"""
Chat and session Pydantic v2 schemas.

Covers:
  - Session create/list/get
  - Chat request (query + optional session + document scope)
  - Chat response (final answer + structured data + citations + agent trace)
  - Streaming event envelope
  - Message history
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseRequest, BaseResponse


# ─────────────────────────────────────────────────────────────────────────────
# Session
# ─────────────────────────────────────────────────────────────────────────────

class SessionCreateRequest(BaseRequest):
    """Create a new chat session scoped to one or more documents."""

    title: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Optional title. Auto-generated from first message if omitted.",
    )
    document_ids: list[UUID] = Field(
        default_factory=list,
        description="Documents to scope this session. Empty = all user documents.",
    )
    session_type: str = Field(
        default="chat",
        description="'chat' | 'quiz' | 'flashcard'",
    )

    @field_validator("session_type")
    @classmethod
    def validate_session_type(cls, v: str) -> str:
        allowed = {"chat", "quiz", "flashcard"}
        if v not in allowed:
            raise ValueError(f"session_type must be one of {allowed}")
        return v


class SessionResponse(BaseResponse):
    """Single session record."""

    id: UUID
    title: Optional[str]
    document_ids: list[UUID]
    session_type: str
    message_count: int
    last_active_at: datetime
    is_archived: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionListResponse(BaseResponse):
    """Paginated session list."""

    sessions: list[SessionResponse]
    total: int
    page: int
    limit: int


# ─────────────────────────────────────────────────────────────────────────────
# Quiz structured output schema
# ─────────────────────────────────────────────────────────────────────────────

class QuizOption(BaseResponse):
    """One MCQ answer option."""

    label: str          # "A", "B", "C", "D"
    text: str
    is_correct: bool


class QuizQuestion(BaseResponse):
    """A single quiz question with metadata."""

    question_number: int
    question_type: str      # "mcq" | "conceptual" | "interview"
    difficulty: str         # "easy" | "medium" | "hard"
    question: str
    options: list[QuizOption] = Field(default_factory=list)   # empty for open-ended
    answer: str             # correct answer or model answer
    explanation: str


class QuizOutput(BaseResponse):
    """Structured output from QuizAgent."""

    topic: str
    difficulty: str
    total_questions: int
    questions: list[QuizQuestion]


# ─────────────────────────────────────────────────────────────────────────────
# Summary structured output schema
# ─────────────────────────────────────────────────────────────────────────────

class SummaryOutput(BaseResponse):
    """Structured output from SummaryAgent."""

    short_summary: str      # 2-3 sentences — for card previews
    detailed_summary: str   # full paragraph(s)
    bullet_points: list[str]
    key_topics: list[str]
    word_count: int


# ─────────────────────────────────────────────────────────────────────────────
# Chat request / response
# ─────────────────────────────────────────────────────────────────────────────

class ChatRequest(BaseRequest):
    """
    Request body for POST /chat.

    session_id: If provided, the conversation continues in that session.
                If omitted, a new session is created automatically.
    document_ids: Scope retrieval to specific documents. Empty = all user docs.
    """

    query: str = Field(
        min_length=1,
        max_length=4000,
        description="The user's natural language query.",
        examples=["Explain the concept of backpropagation."],
    )
    session_id: Optional[UUID] = Field(
        default=None,
        description="Continue an existing session. Omit to start a new one.",
    )
    document_ids: list[UUID] = Field(
        default_factory=list,
        description="Limit context to these documents. Empty = all user documents.",
    )

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()


class CitationResponse(BaseResponse):
    """One source citation in the final response."""

    position: int
    document_id: UUID
    original_filename: str
    page_number: Optional[int]
    chunk_index: int
    similarity_score: float


class AgentTraceEntry(BaseResponse):
    """Lightweight trace of one agent's execution (surfaced in the API response)."""

    agent_name: str
    status: str             # "success" | "error" | "skipped"
    latency_ms: Optional[int]
    token_input: Optional[int]
    token_output: Optional[int]


class ChatResponse(BaseResponse):
    """
    Full response from POST /chat.

    structured_data holds the quiz/summary payload when intent is not "qa".
    agent_trace lists the agents that ran, in order — useful for debugging.
    """

    session_id: UUID
    message_id: UUID
    query: str
    intent: str             # "qa" | "summary" | "quiz"
    response: str           # The final natural-language answer
    structured_data: Optional[dict[str, Any]] = None   # QuizOutput or SummaryOutput
    citations: list[CitationResponse] = Field(default_factory=list)
    agent_trace: list[AgentTraceEntry] = Field(default_factory=list)
    latency_ms: int
    token_count: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
# Message history
# ─────────────────────────────────────────────────────────────────────────────

class MessageResponse(BaseResponse):
    """One turn in a conversation."""

    id: UUID
    session_id: UUID
    role: str               # "user" | "assistant"
    content: str
    content_type: str
    intent: Optional[str]
    structured_data: Optional[dict[str, Any]]
    sources: Optional[list[dict[str, Any]]]
    agent_path: Optional[list[str]]
    latency_ms: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageHistoryResponse(BaseResponse):
    """Paginated message history for a session."""

    session_id: UUID
    messages: list[MessageResponse]
    total: int
    page: int
    limit: int


# ─────────────────────────────────────────────────────────────────────────────
# Streaming event envelope
# ─────────────────────────────────────────────────────────────────────────────

class StreamEvent(BaseResponse):
    """
    One Server-Sent Event payload.

    event_type:
      "agent_start"    — an agent began executing
      "agent_end"      — an agent completed
      "token"          — a streamed LLM token (partial response)
      "final"          — the full ChatResponse (last event)
      "error"          — pipeline error
    """

    event_type: str
    data: dict[str, Any]
