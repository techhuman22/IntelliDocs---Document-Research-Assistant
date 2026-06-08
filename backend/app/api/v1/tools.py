"""
Tools API — dedicated endpoints for Summary, Quiz, and Flashcards.

Each endpoint:
  1. Fetches ALL document chunks directly from DB (not similarity search)
     — ensures full document coverage for summary/quiz/flashcards
  2. Calls the appropriate LLM agent directly
  3. Returns structured JSON ready for the frontend
"""

import time
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import (
    FLASHCARD_HUMAN,
    FLASHCARD_SYSTEM,
    SUMMARY_HUMAN,
    SUMMARY_SYSTEM,
    QUIZ_HUMAN,
    QUIZ_SYSTEM,
)
from app.api.dependencies import (
    get_current_active_user,
    get_db,
)
from app.config.settings import settings
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, User

logger = get_logger(__name__)
router = APIRouter()


# ── Request / Response schemas ────────────────────────────────────────────────

class ToolRequest(BaseModel):
    document_ids: list[str] = Field(default_factory=list)
    query: str = ""
    num_items: int = Field(default=5, ge=1, le=20)
    difficulty: str = Field(default="mixed")


class SummaryResponse(BaseModel):
    short_summary: str
    detailed_summary: str
    bullet_points: list[str]
    key_topics: list[str]
    word_count: int
    latency_ms: int


class QuizOption(BaseModel):
    label: str
    text: str
    is_correct: bool


class QuizQuestion(BaseModel):
    question_number: int
    question_type: str
    difficulty: str
    question: str
    options: list[QuizOption]
    answer: str
    explanation: str


class QuizResponse(BaseModel):
    topic: str
    difficulty: str
    total_questions: int
    questions: list[QuizQuestion]
    latency_ms: int


class Flashcard(BaseModel):
    front: str
    back: str
    topic: str


class FlashcardsResponse(BaseModel):
    cards: list[Flashcard]
    total: int
    latency_ms: int


# ── Structured LLM schemas ────────────────────────────────────────────────────

class _SummaryLLM(BaseModel):
    short_summary: str
    detailed_summary: str
    bullet_points: list[str]
    key_topics: list[str]
    word_count: int


class _QuizOptionLLM(BaseModel):
    label: str
    text: str
    is_correct: bool


class _QuizQuestionLLM(BaseModel):
    question_number: int
    question_type: str
    difficulty: str
    question: str
    options: list[_QuizOptionLLM] = Field(default_factory=list)
    answer: str
    explanation: str


class _QuizLLM(BaseModel):
    topic: str
    difficulty: str
    total_questions: int
    questions: list[_QuizQuestionLLM]


class _FlashcardLLM(BaseModel):
    front: str
    back: str
    topic: str


class _FlashcardsLLM(BaseModel):
    cards: list[_FlashcardLLM]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_llm(temperature: float = 0.3) -> ChatGroq:
    return ChatGroq(
        model=settings.GROQ_MODEL,
        api_key=settings.GROQ_API_KEY,
        temperature=temperature,
        max_retries=settings.LLM_MAX_RETRIES,
    )


async def _fetch_context(
    db: AsyncSession,
    user_id: str,
    document_ids: list[str],
    max_chars: int = 20000,
) -> str:
    """
    Fetch ALL chunks for the selected documents directly from DB.
    Ordered by document + chunk_index so context reads naturally.
    Returns a single context string ready for the LLM.

    This bypasses similarity search — for summary/quiz/flashcards we want
    the FULL document content, not just semantically similar chunks.
    """
    user_uuid = uuid.UUID(user_id)

    stmt = (
        select(
            DocumentChunk.content,
            DocumentChunk.chunk_index,
            DocumentChunk.page_number,
            Document.original_filename,
        )
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            DocumentChunk.user_id == user_uuid,
            Document.user_id == user_uuid,
        )
        .order_by(Document.original_filename, DocumentChunk.chunk_index)
    )

    # Filter to selected documents if specified
    if document_ids:
        doc_uuids = [uuid.UUID(did) for did in document_ids]
        stmt = stmt.where(DocumentChunk.document_id.in_(doc_uuids))

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return ""

    # Build context string — group by filename, include chunk content
    parts = []
    current_file = None
    char_count = 0

    for content, chunk_idx, page_num, filename in rows:
        if char_count >= max_chars:
            break

        if filename != current_file:
            current_file = filename
            header = f"\n\n=== Document: {filename} ===\n"
            parts.append(header)
            char_count += len(header)

        page_note = f" [Page {page_num}]" if page_num else ""
        chunk_text = f"[Chunk {chunk_idx}{page_note}]\n{content}\n"

        remaining = max_chars - char_count
        if len(chunk_text) > remaining:
            chunk_text = chunk_text[:remaining]

        parts.append(chunk_text)
        char_count += len(chunk_text)

    return "".join(parts).strip()


# ── Summary endpoint ──────────────────────────────────────────────────────────

@router.post("/tools/summary", response_model=SummaryResponse)
async def generate_summary(
    body: ToolRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> SummaryResponse:
    t = time.perf_counter()

    context = await _fetch_context(db, str(current_user.id), body.document_ids)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No document content found. Please upload a document and click 'Process' on the Documents page first.",
        )

    llm = _make_llm(0.3).with_structured_output(_SummaryLLM)
    result: _SummaryLLM = await llm.ainvoke([
        SystemMessage(content=SUMMARY_SYSTEM),
        HumanMessage(content=SUMMARY_HUMAN.format(
            query="Generate a comprehensive summary of this document.",
            context=context[:16000],
        )),
    ])

    logger.info("tools_summary_done", user_id=str(current_user.id))
    return SummaryResponse(
        **result.model_dump(),
        latency_ms=int((time.perf_counter() - t) * 1000),
    )


# ── Quiz endpoint ─────────────────────────────────────────────────────────────

@router.post("/tools/quiz", response_model=QuizResponse)
async def generate_quiz(
    body: ToolRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> QuizResponse:
    t = time.perf_counter()

    context = await _fetch_context(db, str(current_user.id), body.document_ids)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No document content found. Please upload a document and click 'Process' on the Documents page first.",
        )

    enriched_query = f"Generate {body.num_items} quiz questions [difficulty: {body.difficulty}]"
    llm = _make_llm(0.4).with_structured_output(_QuizLLM)
    result: _QuizLLM = await llm.ainvoke([
        SystemMessage(content=QUIZ_SYSTEM),
        HumanMessage(content=QUIZ_HUMAN.format(
            query=enriched_query,
            context=context[:16000],
        )),
    ])

    logger.info("tools_quiz_done", user_id=str(current_user.id), questions=result.total_questions)
    return QuizResponse(
        **result.model_dump(),
        latency_ms=int((time.perf_counter() - t) * 1000),
    )


# ── Flashcards endpoint ───────────────────────────────────────────────────────

@router.post("/tools/flashcards", response_model=FlashcardsResponse)
async def generate_flashcards(
    body: ToolRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> FlashcardsResponse:
    t = time.perf_counter()

    context = await _fetch_context(db, str(current_user.id), body.document_ids)

    if not context:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No document content found. Please upload a document and click 'Process' on the Documents page first.",
        )

    llm = _make_llm(0.4).with_structured_output(_FlashcardsLLM)
    result: _FlashcardsLLM = await llm.ainvoke([
        SystemMessage(content=FLASHCARD_SYSTEM),
        HumanMessage(content=FLASHCARD_HUMAN.format(
            context=context[:16000],
            num_cards=body.num_items,
        )),
    ])

    logger.info("tools_flashcards_done", user_id=str(current_user.id), cards=len(result.cards))
    return FlashcardsResponse(
        cards=[Flashcard(**c.model_dump()) for c in result.cards],
        total=len(result.cards),
        latency_ms=int((time.perf_counter() - t) * 1000),
    )
