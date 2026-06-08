"""
Summary Agent — generates structured multi-format summaries via Gemini.

Three summary formats:
  short_summary   → 2-3 sentences, suitable for preview cards
  detailed_summary → comprehensive coverage of the document content
  bullet_points   → 5-8 actionable insights
  key_topics      → main subjects covered

Why structured output?
  Using llm.with_structured_output() forces Gemini to emit valid JSON
  matching our Pydantic schema. This eliminates output parsing errors
  and makes the quiz/summary data directly usable by the frontend
  without additional transformation.

Only runs when intent == "summary".
Skipped (state unchanged) for "qa" and "quiz" intent.
"""

import json
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from app.agents.prompts import SUMMARY_HUMAN, SUMMARY_SYSTEM
from app.agents.state import AgentState
from app.config.settings import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Structured output schema for the LLM ─────────────────────────────────────

class _SummaryStructured(BaseModel):
    """Pydantic schema passed to llm.with_structured_output()."""

    short_summary: str = Field(description="2-3 sentence executive summary.")
    detailed_summary: str = Field(description="Comprehensive multi-paragraph summary.")
    bullet_points: list[str] = Field(description="5-8 key takeaways as bullet items.")
    key_topics: list[str] = Field(description="3-6 main topics discussed.")
    word_count: int = Field(description="Approximate word count of the detailed summary.")


# ── Node ──────────────────────────────────────────────────────────────────────

async def summary_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    LangGraph node: generate a structured summary from retrieved context.

    Reads:   state["query"], state["context"]
    Writes:  state["summary"], state["agent_trace"], state["metadata"]
    """
    t_start = time.perf_counter()
    agent_name = "summary"

    logger.info(
        "summary_agent_start",
        session_id=state["session_id"],
        context_len=len(state.get("context", "")),
    )

    context = state.get("context", "")
    if not context:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.warning("summary_agent_no_context", session_id=state["session_id"])
        return {
            "summary": {
                "short_summary": "No document content was found to summarize.",
                "detailed_summary": "The retrieval step found no relevant content. Please ensure your documents are indexed.",
                "bullet_points": [],
                "key_topics": [],
                "word_count": 0,
            },
            "agent_trace": [
                {
                    "agent_name": agent_name,
                    "status": "skipped",
                    "latency_ms": latency_ms,
                    "token_input": None,
                    "token_output": None,
                }
            ],
            "metadata": {**state.get("metadata", {}), "summary_latency_ms": latency_ms},
        }

    try:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0.3,
            max_retries=settings.LLM_MAX_RETRIES,
        )

        structured_llm = llm.with_structured_output(_SummaryStructured)

        human_text = SUMMARY_HUMAN.format(
            query=state["query"],
            context=context[:settings.CONTEXT_MAX_TOKENS * 4],  # ~max chars before token limit
        )

        messages_for_llm = [
            SystemMessage(content=SUMMARY_SYSTEM),
            HumanMessage(content=human_text),
        ]

        result: _SummaryStructured = await structured_llm.ainvoke(messages_for_llm)
        summary_dict = result.model_dump()

        latency_ms = int((time.perf_counter() - t_start) * 1000)

        logger.info(
            "summary_agent_done",
            session_id=state["session_id"],
            word_count=summary_dict.get("word_count", 0),
            latency_ms=latency_ms,
        )

        return {
            "summary": summary_dict,
            "agent_trace": [
                {
                    "agent_name": agent_name,
                    "status": "success",
                    "latency_ms": latency_ms,
                    "token_input": None,
                    "token_output": None,
                }
            ],
            "metadata": {
                **state.get("metadata", {}),
                "summary_latency_ms": latency_ms,
                "summary_word_count": summary_dict.get("word_count", 0),
            },
        }

    except Exception as exc:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.error(
            "summary_agent_error",
            session_id=state["session_id"],
            error=str(exc),
            exc_info=True,
        )
        return {
            "summary": None,
            "error": f"Summary generation failed: {exc}",
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
                "summary_latency_ms": latency_ms,
                "summary_error": str(exc),
            },
        }
