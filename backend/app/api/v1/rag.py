"""
RAG API routes:

  POST /documents/process/{document_id}  — trigger background indexing
  GET  /documents/{document_id}/chunks   — paginated chunk listing
  POST /retrieval/search                 — semantic similarity search

All routes require authentication (get_current_active_user).

Route design decisions:
  - Process trigger is a POST (not GET) because it has side-effects.
  - The response to /process tells whether the task was queued or already ready,
    so clients don't need to poll Celery directly.
  - /retrieval/search is scoped to the authenticated user — users cannot
    retrieve chunks from other users' documents even if they know a document_id.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import (
    get_current_active_user,
    get_db,
    get_document_service,
    get_embedding_service,
    get_retrieval_service,
    get_vector_repository,
)
from app.core.exceptions import DocumentNotFoundException, ForbiddenException
from app.core.logging import get_logger
from app.db.models import User
from app.db.repositories.document_repository import DocumentRepository
from app.schemas.rag import (
    ChunkListResponse,
    ChunkResponse,
    ProcessingStatusResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from app.services.context_builder_service import ContextBuilderService
from app.services.document_service import DocumentService
from app.services.retrieval_service import RetrievalService

logger = get_logger(__name__)

router = APIRouter()

# ── Trigger document processing ───────────────────────────────────────────────

@router.post(
    "/documents/process/{document_id}",
    response_model=ProcessingStatusResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger RAG indexing for a document",
    description=(
        "Enqueues a background Celery task to parse, chunk, embed, and store "
        "the document in pgvector. If the document is already 'ready', returns "
        "immediately without re-processing (use force=true to override)."
    ),
)
async def trigger_document_processing(
    document_id: UUID,
    force: bool = Query(
        default=False,
        description="Re-process even if the document is already ready.",
    ),
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
    db: AsyncSession = Depends(get_db),
) -> ProcessingStatusResponse:
    """
    Queue a document for RAG indexing.

    The actual processing runs in a Celery worker.
    This endpoint returns immediately (HTTP 202) with the current status.
    """
    # Ownership check via document_service (raises DocumentNotFoundException if missing/wrong user)
    document = await document_service.get_document(
        document_id=document_id,
        user=current_user,
    )

    # Skip re-queue if already ready and force not requested
    if document.status == "ready" and not force:
        return ProcessingStatusResponse(
            document_id=document_id,
            status="ready",
            message="Document is already indexed and ready for retrieval.",
            chunk_count=document.chunk_count or 0,
        )

    if document.status == "processing":
        return ProcessingStatusResponse(
            document_id=document_id,
            status="processing",
            message="Document is already being processed.",
            chunk_count=0,
        )

    # Process inline (no Celery needed in dev mode)
    from app.workers.tasks import run_document_processing_inline
    import asyncio

    logger.info(
        "document_processing_started",
        document_id=str(document_id),
        user_id=str(current_user.id),
        force=force,
    )

    # Run inline and await result
    try:
        chunk_count = await run_document_processing_inline(
            str(document_id), str(current_user.id)
        )
        return ProcessingStatusResponse(
            document_id=document_id,
            status="ready",
            message=f"Document indexed successfully with {chunk_count} chunks.",
            chunk_count=chunk_count,
        )
    except Exception as exc:
        logger.error("document_processing_failed", document_id=str(document_id), error=str(exc))
        return ProcessingStatusResponse(
            document_id=document_id,
            status="failed",
            message=f"Processing failed: {exc}",
            chunk_count=0,
        )


# ── List chunks ───────────────────────────────────────────────────────────────

@router.get(
    "/documents/{document_id}/chunks",
    response_model=ChunkListResponse,
    summary="List chunks for a document",
    description="Paginated list of stored text chunks for an indexed document.",
)
async def list_document_chunks(
    document_id: UUID,
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page."),
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
    vector_repo=Depends(get_vector_repository),
) -> ChunkListResponse:
    """
    Return paginated chunks for a document.

    The document must be owned by the authenticated user and have status='ready'.
    """
    # Ownership check
    document = await document_service.get_document(
        document_id=document_id,
        user=current_user,
    )

    if document.status != "ready":
        from app.core.exceptions import ValidationException
        raise ValidationException(
            f"Document is not ready for retrieval (status='{document.status}'). "
            "Trigger processing first via POST /documents/process/{document_id}."
        )

    offset = (page - 1) * limit
    chunks_orm, total = await vector_repo.get_chunks_by_document(
        document_id=str(document_id),
        user_id=str(current_user.id),
        limit=limit,
        offset=offset,
    )

    return ChunkListResponse(
        document_id=document_id,
        original_filename=document.original_filename,
        chunks=[ChunkResponse.model_validate(c) for c in chunks_orm],
        total_chunks=total,
        page=page,
        limit=limit,
    )


# ── Similarity search ─────────────────────────────────────────────────────────

@router.post(
    "/retrieval/search",
    response_model=RetrievalSearchResponse,
    summary="Semantic similarity search",
    description=(
        "Embeds the query using Gemini text-embedding-004 and retrieves "
        "the most relevant chunks from the user's indexed documents via pgvector."
    ),
)
async def retrieval_search(
    request: RetrievalSearchRequest,
    current_user: User = Depends(get_current_active_user),
    retrieval_service: RetrievalService = Depends(get_retrieval_service),
) -> RetrievalSearchResponse:
    """
    Semantic search over the authenticated user's document chunks.

    Returns ranked chunks, a pre-built LLM context string, and citations.
    """
    retrieved_chunks, retrieval_metadata = await retrieval_service.search(
        query=request.query,
        user_id=str(current_user.id),
        document_ids=request.document_ids or None,
        top_k=request.top_k,
        similarity_threshold=request.similarity_threshold,
    )

    # Build context string (respects CONTEXT_MAX_TOKENS)
    context_builder = ContextBuilderService()
    built = context_builder.build(query=request.query, chunks=retrieved_chunks)

    return RetrievalSearchResponse(
        query=request.query,
        chunks=retrieved_chunks if request.include_metadata else [
            c.model_copy(update={"chunk_metadata": {}}) for c in retrieved_chunks
        ],
        total_found=len(retrieved_chunks),
        context=built.context_text,
        citations=built.citations,
        retrieval_metadata=retrieval_metadata,
    )
