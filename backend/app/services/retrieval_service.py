"""
Retrieval service — converts a natural language query into ranked chunks.

Pipeline:
  1. Embed the query using EmbeddingService (task_type=retrieval_query)
  2. Run cosine similarity search via VectorRepository
  3. Filter by similarity_threshold, take top_k
  4. Convert DB rows to RetrievedChunk Pydantic models

This service is stateless and has no awareness of context building —
that is ContextBuilderService's responsibility.
"""

import time
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.repositories.vector_repository import VectorRepository
from app.schemas.rag import RetrievedChunk
from app.services.embedding_service import EmbeddingService

logger = get_logger(__name__)


class RetrievalService:
    """
    Embeds a query and retrieves the most relevant document chunks.

    Designed for use by:
      - The /retrieval/search API endpoint directly
      - The LangGraph retrieval agent (Phase 5)
      - The ContextBuilderService
    """

    def __init__(
        self,
        session: AsyncSession,
        embedding_service: EmbeddingService,
    ) -> None:
        self._session = session
        self._vector_repo = VectorRepository(session)
        self._embedder = embedding_service

    async def search(
        self,
        *,
        query: str,
        user_id: str,
        document_ids: Optional[list[UUID]] = None,
        top_k: int = 8,
        similarity_threshold: float = 0.70,
    ) -> tuple[list[RetrievedChunk], dict]:
        """
        Embed query and retrieve similar chunks.

        Args:
            query:                Natural language query.
            user_id:              Restricts search to user's own documents.
            document_ids:         Optional scope — UUIDs of documents to search within.
            top_k:                Maximum number of chunks to return (1–20).
            similarity_threshold: Minimum similarity score to include a result.

        Returns:
            Tuple of:
              - list[RetrievedChunk]: Ranked by similarity descending.
              - dict: retrieval_metadata (timing, counts) for the API response.
        """
        t_start = time.perf_counter()

        # ── 1. Embed query ────────────────────────────────────────────────────
        t_embed_start = time.perf_counter()
        query_vector = await self._embedder.embed_query(query)
        embedding_ms = round((time.perf_counter() - t_embed_start) * 1000, 2)

        # ── 2. Vector search ──────────────────────────────────────────────────
        t_search_start = time.perf_counter()
        doc_id_strings = (
            [str(did) for did in document_ids] if document_ids else None
        )
        raw_results = await self._vector_repo.similarity_search(
            query_embedding=query_vector,
            user_id=user_id,
            document_ids=doc_id_strings,
            top_k=top_k,
            similarity_threshold=similarity_threshold,
        )
        search_ms = round((time.perf_counter() - t_search_start) * 1000, 2)

        # ── 3. Map to Pydantic models ─────────────────────────────────────────
        retrieved: list[RetrievedChunk] = []
        for chunk_orm, similarity, original_filename in raw_results:
            retrieved.append(
                RetrievedChunk(
                    chunk_id=chunk_orm.id,
                    document_id=chunk_orm.document_id,
                    original_filename=original_filename,
                    chunk_index=chunk_orm.chunk_index,
                    content=chunk_orm.content,
                    similarity_score=round(similarity, 4),
                    page_number=chunk_orm.page_number,
                    chunk_metadata=chunk_orm.chunk_metadata or {},
                )
            )

        total_ms = round((time.perf_counter() - t_start) * 1000, 2)

        metadata = {
            "total_latency_ms": total_ms,
            "embedding_ms": embedding_ms,
            "search_ms": search_ms,
            "candidates_searched": len(raw_results),
            "chunks_returned": len(retrieved),
            "query_length": len(query),
            "document_scope": len(document_ids) if document_ids else "all",
        }

        logger.info(
            "retrieval_search_complete",
            user_id=user_id,
            query_len=len(query),
            returned=len(retrieved),
            **{f"meta_{k}": v for k, v in metadata.items()},
        )

        return retrieved, metadata
