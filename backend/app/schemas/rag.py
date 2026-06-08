"""
RAG pipeline Pydantic v2 schemas.

Covers:
  - Document processing trigger and status responses
  - Retrieval search request and response
  - Chunk listing
  - Context builder output (consumed by LangGraph agents in Phase 5)
"""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.base import BaseRequest, BaseResponse


# ─────────────────────────────────────────────────────────────────────────────
# Processing
# ─────────────────────────────────────────────────────────────────────────────

class ProcessingStatusResponse(BaseResponse):
    """
    Response for POST /documents/process/{document_id}.
    Tells the client whether processing was triggered or already complete.
    """

    document_id: UUID
    status: str                          # 'pending' | 'processing' | 'ready' | 'failed'
    message: str
    chunk_count: int = 0
    error_message: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Chunks
# ─────────────────────────────────────────────────────────────────────────────

class ChunkResponse(BaseResponse):
    """Single document chunk — returned by the chunk listing endpoint."""

    id: UUID
    document_id: UUID
    chunk_index: int
    content: str
    token_count: int
    char_count: Optional[int]
    page_number: Optional[int]
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = {"from_attributes": True}


class ChunkListResponse(BaseResponse):
    """Paginated chunk list for GET /documents/{id}/chunks."""

    document_id: UUID
    original_filename: str
    chunks: list[ChunkResponse]
    total_chunks: int
    page: int
    limit: int


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval / Search
# ─────────────────────────────────────────────────────────────────────────────

class RetrievalSearchRequest(BaseRequest):
    """
    Request body for POST /retrieval/search.

    document_ids scopes the search to specific documents.
    If empty, searches across ALL of the user's documents.
    """

    query: str = Field(
        min_length=1,
        max_length=2000,
        description="Natural language query to search for.",
        examples=["What are the main findings of the report?"],
    )
    document_ids: list[UUID] = Field(
        default_factory=list,
        description="Limit search to these document IDs. Empty = all user documents.",
    )
    top_k: int = Field(
        default=8,
        ge=1,
        le=20,
        description="Number of chunks to retrieve (1–20).",
    )
    similarity_threshold: float = Field(
        default=0.70,
        ge=0.0,
        le=1.0,
        description="Minimum cosine similarity score to include a chunk (0.0–1.0).",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include chunk metadata (page number, section, etc.) in response.",
    )

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()


class RetrievedChunk(BaseResponse):
    """
    A single chunk returned by the retrieval pipeline.
    Includes the similarity score and source document information.
    """

    chunk_id: UUID
    document_id: UUID
    original_filename: str              # denormalized for display — avoids a join
    chunk_index: int
    content: str
    similarity_score: float = Field(description="Cosine similarity (0.0 – 1.0).")
    page_number: Optional[int] = None
    chunk_metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalSearchResponse(BaseResponse):
    """
    Full response from POST /retrieval/search.
    Contains ranked chunks and a pre-built LLM context string.
    """

    query: str
    chunks: list[RetrievedChunk]
    total_found: int
    context: str = Field(
        description=(
            "Pre-formatted context string ready for injection into an LLM prompt. "
            "Chunks are concatenated with separators and source citations."
        )
    )
    citations: list[dict[str, Any]] = Field(
        description="Source references: [{doc_name, page, chunk_index, score}]"
    )
    retrieval_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Debug metadata: latency_ms, embedding_ms, search_ms, etc.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Context Builder output (used internally by LangGraph agents)
# ─────────────────────────────────────────────────────────────────────────────

class BuiltContext(BaseResponse):
    """
    The structured context object passed from the Retrieval Agent to
    downstream LangGraph agents (Summary, Quiz, Flashcard, etc.).

    This is not a direct API response — it is the internal data contract
    between the retrieval pipeline and the agent layer.
    """

    query: str
    context_text: str                   # ready-to-inject LLM context string
    chunks: list[RetrievedChunk]        # full chunk objects for agent reasoning
    citations: list[dict[str, Any]]     # source references
    total_tokens_estimate: int          # approximate token count of context_text
    is_sufficient: bool                 # True if similarity scores are above threshold
    sufficiency_score: float            # avg similarity of top chunks (0.0–1.0)
