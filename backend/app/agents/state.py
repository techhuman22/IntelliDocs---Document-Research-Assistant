"""
AgentState — the single shared data structure that flows through the LangGraph workflow.

Why TypedDict (not Pydantic)?
  LangGraph requires TypedDict for its state management. It uses the type annotations
  to understand how to merge partial updates from each node. Specifically:
    - Regular fields are replaced on update (last-write-wins)
    - Fields annotated with `Annotated[..., reducer_fn]` are merged using the reducer

Why these fields?

  user_id      — Ownership boundary. Every retrieval query and DB write is scoped
                 to this user. Passed through so nodes don't need the HTTP request.

  session_id   — Links all agent logs and messages to a single conversation turn.
                 Created before graph invocation and stored in DB after.

  query        — The raw user input. Preserved unchanged through the pipeline so
                 the Final Response agent can include the original question.

  document_ids — Optional scope for retrieval. Empty list = search all user docs.

  intent       — Set by RouterAgent. Controls conditional branching:
                 "qa" → straight to FinalResponse
                 "summary" → SummaryAgent → FinalResponse
                 "quiz" → QuizAgent → FinalResponse

  retrieved_chunks — List of RetrievedChunk from pgvector search. Carried through
                 so both the SummaryAgent/QuizAgent and FinalResponseAgent can
                 reference source material and citations.

  context      — Pre-formatted LLM context string from ContextBuilderService.
                 Injected directly into agent prompts.

  summary      — dict representation of SummaryOutput (set by SummaryAgent, None otherwise).

  quiz         — dict representation of QuizOutput (set by QuizAgent, None otherwise).

  final_response — The polished answer returned to the user.

  messages     — LangChain message history with `add_messages` reducer so each node
                 can append without overwriting previous turns. Used for multi-turn
                 conversation context injection into prompts.

  agent_trace  — List of AgentTraceEntry dicts accumulated across the pipeline.
                 Annotated with `operator.add` so each node appends its entry.

  metadata     — Flexible dict for timing, token counts, and debug info. Each
                 node merges its data into this dict.

  error        — If any node hits an unrecoverable failure it sets this field.
                 FinalResponseAgent checks it and returns a graceful error message.
"""

import operator
from typing import Annotated, Any, Optional
from typing_extensions import TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from app.schemas.rag import RetrievedChunk


class AgentState(TypedDict):
    # ── Identity ──────────────────────────────────────────────────────────────
    user_id: str
    session_id: str

    # ── Input ─────────────────────────────────────────────────────────────────
    query: str
    document_ids: list[str]

    # ── Routing ───────────────────────────────────────────────────────────────
    intent: str  # "qa" | "summary" | "quiz" | "unknown"

    # ── Retrieval ─────────────────────────────────────────────────────────────
    retrieved_chunks: list[RetrievedChunk]
    context: str

    # ── Agent outputs ─────────────────────────────────────────────────────────
    summary: Optional[dict[str, Any]]   # SummaryOutput.model_dump()
    quiz: Optional[dict[str, Any]]      # QuizOutput.model_dump()
    final_response: str

    # ── Conversation history ──────────────────────────────────────────────────
    # add_messages reducer: each node appends instead of replacing
    messages: Annotated[list[BaseMessage], add_messages]

    # ── Observability ─────────────────────────────────────────────────────────
    # operator.add reducer: each node appends its trace entry to the list
    agent_trace: Annotated[list[dict[str, Any]], operator.add]

    # metadata is merged per-node via a helper — stored as a plain dict here
    metadata: dict[str, Any]

    # ── Error state ───────────────────────────────────────────────────────────
    error: Optional[str]


def initial_state(
    user_id: str,
    session_id: str,
    query: str,
    document_ids: list[str],
    history_messages: list[BaseMessage],
) -> AgentState:
    """
    Build the starting AgentState for a new query.

    history_messages: Last N messages from the ChatSession, loaded from DB.
    These are injected into `messages` so agents can reference conversation history.
    """
    return AgentState(
        user_id=user_id,
        session_id=session_id,
        query=query,
        document_ids=document_ids,
        intent="unknown",
        retrieved_chunks=[],
        context="",
        summary=None,
        quiz=None,
        final_response="",
        messages=history_messages,
        agent_trace=[],
        metadata={},
        error=None,
    )
