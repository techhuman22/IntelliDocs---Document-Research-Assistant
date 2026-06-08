"""
Router Agent — classifies user intent to control workflow branching.

Model choice:
  Uses gemini-1.5-flash (via settings.GEMINI_FLASH_MODEL) for classification
  because it's a simple single-token output task. Flash is ~10× cheaper and
  ~3× faster than Pro, which matters here since EVERY query goes through routing.

  Falls back to settings.GEMINI_MODEL (Pro) if the flash model isn't configured.

Output:
  Sets state["intent"] to one of: "qa" | "summary" | "quiz"

Error strategy:
  If Gemini is unavailable, defaults to intent="qa" so the pipeline
  continues rather than failing completely. The error is recorded in
  state["error"] and the agent_trace.
"""

import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq

from app.agents.prompts import ROUTER_HUMAN, ROUTER_SYSTEM
from app.agents.state import AgentState
from app.config.settings import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_VALID_INTENTS = {"qa", "summary", "quiz"}
_DEFAULT_INTENT = "qa"


def _format_history(state: AgentState) -> str:
    """Format the last N messages as a simple text string for the router prompt."""
    messages = state.get("messages", [])
    if not messages:
        return "(no prior conversation)"
    # Use last 6 messages (3 turns) for context — more than that confuses routing
    recent = messages[-6:]
    lines = []
    for msg in recent:
        role = "User" if isinstance(msg, HumanMessage) else "Assistant"
        lines.append(f"{role}: {msg.content[:200]}")  # truncate long messages
    return "\n".join(lines)


async def router_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    LangGraph node: classify the user's intent.

    Reads:   state["query"], state["messages"]
    Writes:  state["intent"], state["agent_trace"], state["metadata"]
    """
    t_start = time.perf_counter()
    agent_name = "router"

    logger.info(
        "router_agent_start",
        session_id=state["session_id"],
        query_len=len(state["query"]),
    )

    try:
        llm = ChatGroq(
            model=settings.GROQ_FAST_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0,
            max_retries=settings.LLM_MAX_RETRIES,
        )

        history_text = _format_history(state)
        human_text = ROUTER_HUMAN.format(
            history=history_text,
            query=state["query"],
        )

        messages_for_llm = [
            SystemMessage(content=ROUTER_SYSTEM),
            HumanMessage(content=human_text),
        ]

        response = await llm.ainvoke(messages_for_llm)
        raw = response.content.strip().lower()

        # Extract the intent — the model should return exactly one word
        intent = _DEFAULT_INTENT
        for candidate in _valid_intents_sorted(raw):
            if candidate in raw:
                intent = candidate
                break

        latency_ms = int((time.perf_counter() - t_start) * 1000)
        token_input = getattr(response, "usage_metadata", {}).get("input_tokens")
        token_output = getattr(response, "usage_metadata", {}).get("output_tokens")

        logger.info(
            "router_agent_done",
            session_id=state["session_id"],
            intent=intent,
            latency_ms=latency_ms,
        )

        return {
            "intent": intent,
            "agent_trace": [
                {
                    "agent_name": agent_name,
                    "status": "success",
                    "latency_ms": latency_ms,
                    "token_input": token_input,
                    "token_output": token_output,
                }
            ],
            "metadata": {
                **state.get("metadata", {}),
                "router_latency_ms": latency_ms,
                "detected_intent": intent,
            },
        }

    except Exception as exc:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.error(
            "router_agent_error",
            session_id=state["session_id"],
            error=str(exc),
        )
        return {
            "intent": _DEFAULT_INTENT,  # safe default
            "error": f"Router failed, defaulting to QA: {exc}",
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
                "router_latency_ms": latency_ms,
                "router_error": str(exc),
            },
        }


def _valid_intents_sorted(raw: str) -> list[str]:
    """Return intents ordered by confidence — prefer longer matches over 'qa' substring."""
    return ["summary", "quiz", "qa"]


def route_after_retrieval(state: AgentState) -> str:
    """
    LangGraph conditional edge function.

    Called after the RetrievalAgent to decide which specialist node runs next.
    Returns the node name as a string — LangGraph maps this to the next node.
    """
    intent = state.get("intent", "qa")

    # Error short-circuit: skip specialist agents if retrieval itself failed
    if state.get("error") and not state.get("context"):
        return "final_response"

    if intent == "summary":
        return "summary"
    elif intent == "quiz":
        return "quiz"
    else:
        return "final_response"
