"""
Retrieval Agent — embeds the query and fetches relevant document chunks.

This node is always the second to run (after Router).
It provides context for all downstream agents regardless of intent.

Design:
  Services are injected via LangGraph's RunnableConfig.configurable dict.
  This avoids coupling the node function to FastAPI's DI system, keeping
  the agent layer usable from both HTTP routes and Celery tasks.

Config keys expected:
  config["configurable"]["retrieval_service"]  — RetrievalService instance
  config["configurable"]["context_builder"]    — ContextBuilderService instance

Output:
  state["retrieved_chunks"] — list of RetrievedChunk
  state["context"]          — formatted context string for LLM injection

Error handling:
  On retrieval failure, sets state["error"] but does NOT raise.
  FinalResponseAgent handles empty context gracefully.
"""

import time
from typing import Any

from langchain_core.runnables import RunnableConfig

from app.agents.state import AgentState
from app.core.logging import get_logger
from app.services.context_builder_service import ContextBuilderService
from app.services.retrieval_service import RetrievalService

logger = get_logger(__name__)


async def retrieval_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    LangGraph node: embed query → similarity search → build context.

    Reads:   state["query"], state["user_id"], state["document_ids"]
    Writes:  state["retrieved_chunks"], state["context"], state["agent_trace"], state["metadata"]
    """
    t_start = time.perf_counter()
    agent_name = "retrieval"

    retrieval_service: RetrievalService = config["configurable"]["retrieval_service"]
    context_builder: ContextBuilderService = config["configurable"]["context_builder"]

    logger.info(
        "retrieval_agent_start",
        session_id=state["session_id"],
        intent=state["intent"],
        document_ids=state["document_ids"],
    )

    try:
        from uuid import UUID
        doc_ids = [UUID(did) for did in state["document_ids"]] if state["document_ids"] else None

        retrieved_chunks, retrieval_metadata = await retrieval_service.search(
            query=state["query"],
            user_id=state["user_id"],
            document_ids=doc_ids,
            top_k=settings_top_k(state),
            similarity_threshold=0.65,  # slightly lower than default to get more context for summaries/quizzes
        )

        # Build the context string and citations
        built = context_builder.build(
            query=state["query"],
            chunks=retrieved_chunks,
        )

        latency_ms = int((time.perf_counter() - t_start) * 1000)

        logger.info(
            "retrieval_agent_done",
            session_id=state["session_id"],
            chunks_found=len(retrieved_chunks),
            context_tokens=built.total_tokens_estimate,
            is_sufficient=built.is_sufficient,
            latency_ms=latency_ms,
        )

        trace_entry = {
            "agent_name": agent_name,
            "status": "success",
            "latency_ms": latency_ms,
            "token_input": None,
            "token_output": None,
        }

        if not retrieved_chunks:
            logger.warning(
                "retrieval_agent_no_results",
                session_id=state["session_id"],
                query=state["query"][:100],
            )

        return {
            "retrieved_chunks": retrieved_chunks,
            "context": built.context_text,
            "agent_trace": [trace_entry],
            "metadata": {
                **state.get("metadata", {}),
                "retrieval_latency_ms": latency_ms,
                "chunks_found": len(retrieved_chunks),
                "context_tokens": built.total_tokens_estimate,
                "is_sufficient": built.is_sufficient,
                "sufficiency_score": built.sufficiency_score,
                **{f"retrieval_{k}": v for k, v in retrieval_metadata.items()},
            },
        }

    except Exception as exc:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.error(
            "retrieval_agent_error",
            session_id=state["session_id"],
            error=str(exc),
            exc_info=True,
        )
        return {
            "retrieved_chunks": [],
            "context": "",
            "error": f"Retrieval failed: {exc}",
            "agent_trace": [
                {
                    "agent_name": agent_name,
                    "status": "error",
                    "latency_ms": latency_ms,
                    "token_input": None,
                    "token_output": None,
                }
            ],
            "metadata": {
                **state.get("metadata", {}),
                "retrieval_latency_ms": latency_ms,
                "retrieval_error": str(exc),
            },
        }


def settings_top_k(state: AgentState) -> int:
    """Return top_k appropriate for the detected intent."""
    intent = state.get("intent", "qa")
    # Summary and quiz need more context than a simple Q&A
    if intent in ("summary", "quiz"):
        return 15
    return 8
