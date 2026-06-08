"""
Final Response Agent — produces the polished user-facing answer.

This is the last node in every path through the workflow.
It receives everything from the pipeline (context, summary, quiz, error state)
and synthesises a single natural-language response.

For QA intent:
  Calls Gemini with the retrieved context and conversation history.
  Cites sources inline with [Source N] notation.

For Summary intent:
  Formats the pre-computed SummaryOutput into readable markdown.
  No additional LLM call needed — the summary agent already did the work.

For Quiz intent:
  Formats the pre-computed QuizOutput into a numbered question list.
  No additional LLM call needed.

For error state:
  Returns an apologetic message with guidance on what to try.
  Does not call Gemini to avoid double-failure.

The distinction between "format" (summary/quiz) and "generate" (qa) paths
matters for cost and latency — summary/quiz only call Gemini once each.
"""

import json
import time
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq

from app.agents.prompts import (
    FINAL_RESPONSE_HUMAN_ERROR,
    FINAL_RESPONSE_HUMAN_QA,
    FINAL_RESPONSE_HUMAN_QUIZ,
    FINAL_RESPONSE_HUMAN_SUMMARY,
    FINAL_RESPONSE_SYSTEM,
)
from app.agents.state import AgentState
from app.config.settings import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


def _format_history(state: AgentState) -> str:
    """Format conversation history for injection into the QA prompt."""
    messages = state.get("messages", [])
    if not messages:
        return "(no prior conversation)"
    recent = messages[-6:]
    lines = []
    for msg in recent:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        lines.append(f"{role}: {msg.content[:300]}")
    return "\n".join(lines)


def _format_summary(summary: dict) -> str:
    """Convert SummaryOutput dict to markdown string."""
    lines = [
        f"## Summary\n\n{summary.get('short_summary', '')}",
        f"\n### Detailed Analysis\n\n{summary.get('detailed_summary', '')}",
        "\n### Key Takeaways\n",
    ]
    for point in summary.get("bullet_points", []):
        lines.append(f"- {point}")
    topics = summary.get("key_topics", [])
    if topics:
        lines.append(f"\n### Main Topics\n{', '.join(topics)}")
    return "\n".join(lines)


def _format_quiz(quiz: dict) -> str:
    """Convert QuizOutput dict to formatted question list."""
    topic = quiz.get("topic", "")
    lines = [f"## Quiz: {topic}\n"]
    for q in quiz.get("questions", []):
        lines.append(f"**Question {q['question_number']}** ({q['difficulty'].capitalize()})")
        lines.append(f"{q['question']}\n")
        for opt in q.get("options", []):
            marker = "✓" if opt["is_correct"] else " "
            lines.append(f"  {opt['label']}) {opt['text']}  {marker if opt['is_correct'] else ''}")
        if not q.get("options"):
            lines.append(f"*Model answer:* {q.get('answer', '')}")
        lines.append(f"\n*Explanation:* {q.get('explanation', '')}\n")
    return "\n".join(lines)


async def final_response_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    LangGraph node: produce the final user-facing response.

    Reads:   ALL state fields (context, summary, quiz, intent, error, messages)
    Writes:  state["final_response"], state["agent_trace"], state["metadata"]
    """
    t_start = time.perf_counter()
    agent_name = "final_response"
    intent = state.get("intent", "qa")

    logger.info(
        "final_response_agent_start",
        session_id=state["session_id"],
        intent=intent,
        has_error=bool(state.get("error")),
    )

    # ── Error path ────────────────────────────────────────────────────────────
    if state.get("error") and not state.get("context"):
        error_msg = state.get("error", "An unknown error occurred.")
        human_text = FINAL_RESPONSE_HUMAN_ERROR.format(
            query=state["query"],
            error=error_msg,
        )
        # Still call Gemini for a graceful error message
        try:
            llm = ChatGroq(
                model=settings.GROQ_FAST_MODEL,
                api_key=settings.GROQ_API_KEY,
                temperature=0,
                max_retries=2,
            )
            response = await llm.ainvoke([
                SystemMessage(content=FINAL_RESPONSE_SYSTEM),
                HumanMessage(content=human_text),
            ])
            final = response.content
        except Exception:
            final = (
                f"I apologize, but I encountered an error processing your request: {error_msg}\n\n"
                "Please try again. If the problem persists, check that your documents are indexed."
            )

        latency_ms = int((time.perf_counter() - t_start) * 1000)
        return _build_return(state, final, agent_name, latency_ms, "error")

    # ── Summary path (no extra LLM call) ──────────────────────────────────────
    if intent == "summary" and state.get("summary"):
        final = _format_summary(state["summary"])
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.info("final_response_summary_formatted", session_id=state["session_id"])
        return _build_return(state, final, agent_name, latency_ms, "success")

    # ── Quiz path (no extra LLM call) ─────────────────────────────────────────
    if intent == "quiz" and state.get("quiz"):
        final = _format_quiz(state["quiz"])
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.info("final_response_quiz_formatted", session_id=state["session_id"])
        return _build_return(state, final, agent_name, latency_ms, "success")

    # ── QA path (Gemini generates the answer) ─────────────────────────────────
    try:
        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0.2,
            max_retries=settings.LLM_MAX_RETRIES,
        )

        context = state.get("context", "")
        if not context:
            context = "No relevant document content was found for this query."

        human_text = FINAL_RESPONSE_HUMAN_QA.format(
            query=state["query"],
            context=context,
            history=_format_history(state),
        )

        messages_for_llm = [
            SystemMessage(content=FINAL_RESPONSE_SYSTEM),
            HumanMessage(content=human_text),
        ]

        response = await llm.ainvoke(messages_for_llm)
        final = response.content

        latency_ms = int((time.perf_counter() - t_start) * 1000)

        logger.info(
            "final_response_agent_done",
            session_id=state["session_id"],
            response_len=len(final),
            latency_ms=latency_ms,
        )

        return _build_return(state, final, agent_name, latency_ms, "success")

    except Exception as exc:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.error(
            "final_response_agent_error",
            session_id=state["session_id"],
            error=str(exc),
            exc_info=True,
        )
        fallback = (
            "I encountered an error generating a response. "
            f"Error: {exc}\n\nPlease try rephrasing your question."
        )
        return _build_return(state, fallback, agent_name, latency_ms, "error")


def _build_return(
    state: AgentState,
    final_response: str,
    agent_name: str,
    latency_ms: int,
    status: str,
) -> dict[str, Any]:
    """Build the state update dict for the final response node."""
    return {
        "final_response": final_response,
        # Append the assistant's response to conversation history
        "messages": [AIMessage(content=final_response)],
        "agent_trace": [
            {
                "agent_name": agent_name,
                "status": status,
                "latency_ms": latency_ms,
                "token_input": None,
                "token_output": None,
            }
        ],
        "metadata": {
            **state.get("metadata", {}),
            "final_response_latency_ms": latency_ms,
        },
    }
