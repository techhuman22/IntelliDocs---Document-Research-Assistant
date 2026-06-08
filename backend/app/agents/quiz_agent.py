"""
Quiz Agent — generates structured assessment questions from document context.

Supports three question types:
  mcq         — Multiple choice with 4 options, one correct
  conceptual  — Open-ended questions requiring understanding
  interview   — Realistic interview questions with model answers

Difficulty levels:
  easy   — Recall, definition, single-concept questions
  medium — Application, comparison, multi-step reasoning
  hard   — Analysis, synthesis, edge-case reasoning

The agent detects the requested question type and difficulty from the user's
query (e.g. "make 5 hard interview questions about transformers") and passes
them as instructions to the LLM.

Why structured output matters here:
  Quiz data (options, correct answers, explanations) is highly structured.
  with_structured_output() prevents the LLM from outputting malformed JSON
  or mixing up fields, which would break the quiz UI rendering.
"""

import re
import time
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from app.agents.prompts import QUIZ_HUMAN, QUIZ_SYSTEM
from app.agents.state import AgentState
from app.config.settings import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ── Structured output schemas ─────────────────────────────────────────────────

class _QuizOptionStructured(BaseModel):
    label: str = Field(description="Option label: A, B, C, or D")
    text: str = Field(description="Option text")
    is_correct: bool = Field(description="True if this is the correct answer")


class _QuizQuestionStructured(BaseModel):
    question_number: int
    question_type: str = Field(description="'mcq', 'conceptual', or 'interview'")
    difficulty: str = Field(description="'easy', 'medium', or 'hard'")
    question: str
    options: list[_QuizOptionStructured] = Field(
        default_factory=list,
        description="Options for MCQ only; empty for open-ended questions",
    )
    answer: str = Field(description="Correct answer or model answer for open-ended")
    explanation: str = Field(description="Why this answer is correct / teaching note")


class _QuizOutputStructured(BaseModel):
    topic: str = Field(description="Main subject of the questions")
    difficulty: str = Field(description="Overall difficulty: easy, medium, hard, or mixed")
    total_questions: int
    questions: list[_QuizQuestionStructured]


# ── Intent parsing helpers ────────────────────────────────────────────────────

def _detect_question_count(query: str) -> int:
    """Extract number of questions from query — default 5."""
    match = re.search(r"\b(\d+)\s*(?:questions?|mcqs?|quizzes?)\b", query, re.I)
    if match:
        return min(int(match.group(1)), 20)  # cap at 20
    return 5


def _detect_difficulty(query: str) -> str:
    """Extract difficulty level from query — default 'mixed'."""
    query_lower = query.lower()
    if "hard" in query_lower or "difficult" in query_lower or "advanced" in query_lower:
        return "hard"
    if "easy" in query_lower or "beginner" in query_lower or "basic" in query_lower:
        return "easy"
    if "medium" in query_lower or "intermediate" in query_lower:
        return "medium"
    return "mixed"


# ── Node ──────────────────────────────────────────────────────────────────────

async def quiz_node(state: AgentState, config: RunnableConfig) -> dict[str, Any]:
    """
    LangGraph node: generate structured quiz questions from retrieved context.

    Reads:   state["query"], state["context"]
    Writes:  state["quiz"], state["agent_trace"], state["metadata"]
    """
    t_start = time.perf_counter()
    agent_name = "quiz"

    logger.info(
        "quiz_agent_start",
        session_id=state["session_id"],
        context_len=len(state.get("context", "")),
    )

    context = state.get("context", "")
    if not context:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.warning("quiz_agent_no_context", session_id=state["session_id"])
        return {
            "quiz": {
                "topic": "Unknown",
                "difficulty": "mixed",
                "total_questions": 0,
                "questions": [],
            },
            "error": "No document content found for quiz generation.",
            "agent_trace": [
                {
                    "agent_name": agent_name,
                    "status": "skipped",
                    "latency_ms": latency_ms,
                    "token_input": None,
                    "token_output": None,
                }
            ],
            "metadata": {**state.get("metadata", {}), "quiz_latency_ms": latency_ms},
        }

    try:
        num_questions = _detect_question_count(state["query"])
        difficulty = _detect_difficulty(state["query"])

        llm = ChatGroq(
            model=settings.GROQ_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=0.4,
            max_retries=settings.LLM_MAX_RETRIES,
        )

        structured_llm = llm.with_structured_output(_QuizOutputStructured)

        # Enrich the query with detected parameters so the LLM doesn't have to infer them
        enriched_query = (
            f"{state['query']} "
            f"[Generate {num_questions} questions, difficulty: {difficulty}]"
        )

        human_text = QUIZ_HUMAN.format(
            query=enriched_query,
            context=context[:settings.CONTEXT_MAX_TOKENS * 4],
        )

        messages_for_llm = [
            SystemMessage(content=QUIZ_SYSTEM),
            HumanMessage(content=human_text),
        ]

        result: _QuizOutputStructured = await structured_llm.ainvoke(messages_for_llm)
        quiz_dict = result.model_dump()

        latency_ms = int((time.perf_counter() - t_start) * 1000)

        logger.info(
            "quiz_agent_done",
            session_id=state["session_id"],
            total_questions=quiz_dict.get("total_questions", 0),
            latency_ms=latency_ms,
        )

        return {
            "quiz": quiz_dict,
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
                "quiz_latency_ms": latency_ms,
                "quiz_total_questions": quiz_dict.get("total_questions", 0),
                "quiz_difficulty": difficulty,
            },
        }

    except Exception as exc:
        latency_ms = int((time.perf_counter() - t_start) * 1000)
        logger.error(
            "quiz_agent_error",
            session_id=state["session_id"],
            error=str(exc),
            exc_info=True,
        )
        return {
            "quiz": None,
            "error": f"Quiz generation failed: {exc}",
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
                "quiz_latency_ms": latency_ms,
                "quiz_error": str(exc),
            },
        }
