"""
Vector repository — pgvector-backed chunk storage and similarity search.

Storage:
  Uses SQLAlchemy Core (INSERT ... VALUES) rather than ORM objects for bulk
  insert because ORM's add() + flush() issues one INSERT per row.
  With 200 chunks that would be 200 round-trips vs. one batch INSERT.

Similarity search:
  pgvector's <=> operator computes cosine distance (0 = identical, 2 = opposite).
  We convert to similarity score: similarity = 1 - cosine_distance.
  The HNSW index built in migration 002 makes this sub-millisecond at scale.

User ownership filtering:
  Every query filters by user_id in addition to document_id.
  This prevents a user from probing another user's chunks even if they
  guess a document UUID — defence in depth alongside the service layer.
"""

import uuid
from typing import Optional

from sqlalchemy import Float, delete, func, select, text, type_coerce
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk
from app.services.chunking_service import TextChunk

logger = get_logger(__name__)


class VectorRepository:
    """
    Handles all DocumentChunk database operations including pgvector search.

    Unlike the generic BaseRepository, VectorRepository uses bulk operations
    and raw SQL fragments for pgvector compatibility — SQLAlchemy's ORM layer
    does not natively understand pgvector operators.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ── Write operations ──────────────────────────────────────────────────────

    async def store_chunks(
        self,
        chunks: list[TextChunk],
        document_id: str,
        user_id: str,
    ) -> int:
        """
        Bulk-insert embedded chunks into document_chunks.

        Uses PostgreSQL's INSERT ... ON CONFLICT DO NOTHING so re-processing
        a document (e.g. after a worker crash and retry) is idempotent.
        The (document_id, chunk_index) unique constraint ensures no duplicates.

        Args:
            chunks:      Embedded TextChunk list (each has .embedding attribute).
            document_id: Parent document UUID string.
            user_id:     Owner user UUID string.

        Returns:
            Number of rows actually inserted (0 if all existed).
        """
        if not chunks:
            return 0

        rows = []
        for chunk in chunks:
            embedding = getattr(chunk, "embedding", None)
            if embedding is None:
                raise ValueError(
                    f"Chunk {chunk.chunk_index} has no embedding — "
                    "run EmbeddingService.embed_chunks() first"
                )
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "document_id": uuid.UUID(document_id),
                    "user_id": uuid.UUID(user_id),
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "content_hash": chunk.content_hash,
                    "token_count": chunk.token_count,
                    "char_count": chunk.char_count,
                    "page_number": chunk.page_number,
                    "embedding": embedding,
                    "chunk_metadata": chunk.chunk_metadata,
                }
            )

        stmt = (
            pg_insert(DocumentChunk)
            .values(rows)
            .on_conflict_do_nothing(index_elements=["document_id", "chunk_index"])
        )
        result = await self._session.execute(stmt)
        inserted = result.rowcount

        logger.info(
            "chunks_stored",
            document_id=document_id,
            attempted=len(chunks),
            inserted=inserted,
        )
        return inserted

    async def delete_by_document_id(
        self,
        document_id: str,
        user_id: str,
    ) -> int:
        """
        Delete all chunks for a document.  user_id filter prevents cross-user deletion.

        Returns:
            Number of rows deleted.
        """
        stmt = (
            delete(DocumentChunk)
            .where(
                DocumentChunk.document_id == uuid.UUID(document_id),
                DocumentChunk.user_id == uuid.UUID(user_id),
            )
            .returning(DocumentChunk.id)
        )
        result = await self._session.execute(stmt)
        deleted = len(result.fetchall())
        logger.info(
            "chunks_deleted",
            document_id=document_id,
            deleted=deleted,
        )
        return deleted

    # ── Read operations ───────────────────────────────────────────────────────

    async def get_chunks_by_document(
        self,
        document_id: str,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DocumentChunk], int]:
        """
        Paginated chunk listing for GET /documents/{id}/chunks.

        Returns (chunks, total_count) tuple so the API can include pagination info.
        """
        doc_uuid = uuid.UUID(document_id)
        user_uuid = uuid.UUID(user_id)

        base_filter = (
            DocumentChunk.document_id == doc_uuid,
            DocumentChunk.user_id == user_uuid,
        )

        count_stmt = select(func.count()).select_from(DocumentChunk).where(*base_filter)
        total: int = (await self._session.execute(count_stmt)).scalar_one()

        chunks_stmt = (
            select(DocumentChunk)
            .where(*base_filter)
            .order_by(DocumentChunk.chunk_index)
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(chunks_stmt)
        chunks = list(result.scalars().all())

        return chunks, total

    async def similarity_search(
        self,
        query_embedding: list[float],
        user_id: str,
        document_ids: Optional[list[str]] = None,
        top_k: int = 8,
        similarity_threshold: float = 0.70,
    ) -> list[tuple[DocumentChunk, float, str]]:
        """
        Cosine similarity search over the HNSW index.

        pgvector's <=> is cosine DISTANCE (0=identical, 2=opposite).
        We convert: similarity = 1 - distance, then filter by threshold.

        Args:
            query_embedding:      768-dim float vector from EmbeddingService.embed_query().
            user_id:              Only search within this user's chunks.
            document_ids:         Optional list of document UUID strings to scope the search.
            top_k:                Maximum results to return.
            similarity_threshold: Minimum similarity score (0.0–1.0).

        Returns:
            List of (DocumentChunk, similarity_score, original_filename) tuples,
            ordered by similarity descending.
            original_filename is denormalized from the Document table join so the
            API response doesn't need a second query.
        """
        user_uuid = uuid.UUID(user_id)

        # cosine distance = 1 - cosine similarity → but pgvector gives 0..2 range
        # so similarity = 1 - (<=> distance)   where distance ∈ [0, 2]
        # We clamp to [0, 1] after the query.
        #
        # IMPORTANT: type_coerce wraps the expression with Float so SQLAlchemy
        # does NOT apply pgvector's Vector type processor to the result column.
        # Without this, the <=> operator inherits the Vector column type and
        # pgvector tries to parse the returned float as a vector string, crashing.
        distance_col = type_coerce(
            DocumentChunk.embedding.op("<=>")(query_embedding),
            Float,
        ).label("cosine_distance")

        stmt = (
            select(
                DocumentChunk,
                distance_col,
                Document.original_filename,
            )
            # Skip loading the embedding column — it's large and causes pgvector
            # type-conversion issues when returned via asyncpg as a native list.
            .options(defer(DocumentChunk.embedding))
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(
                DocumentChunk.user_id == user_uuid,
                Document.user_id == user_uuid,   # belt-and-suspenders ownership check
                Document.status == "ready",       # only search indexed documents
            )
        )

        # Scope to specific documents if provided
        if document_ids:
            doc_uuids = [uuid.UUID(did) for did in document_ids]
            stmt = stmt.where(DocumentChunk.document_id.in_(doc_uuids))

        # Order by cosine distance (ascending = most similar first)
        # and limit to a larger pool before similarity threshold filtering
        # (we request top_k * 3 to give the threshold filter enough candidates)
        stmt = stmt.order_by(distance_col).limit(top_k * 3)

        result = await self._session.execute(stmt)
        rows = result.all()

        # Convert distance → similarity, apply threshold, take top_k
        output: list[tuple[DocumentChunk, float, str]] = []
        for chunk, distance, original_filename in rows:
            similarity = max(0.0, 1.0 - float(distance))
            if similarity >= similarity_threshold:
                output.append((chunk, similarity, original_filename))
            if len(output) >= top_k:
                break

        logger.info(
            "similarity_search_done",
            user_id=user_id,
            document_ids=document_ids,
            candidates=len(rows),
            returned=len(output),
            top_k=top_k,
            threshold=similarity_threshold,
        )

        return output

    async def get_chunk_count_for_document(
        self,
        document_id: str,
        user_id: str,
    ) -> int:
        """Return total number of stored chunks for a document."""
        stmt = select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id == uuid.UUID(document_id),
            DocumentChunk.user_id == uuid.UUID(user_id),
        )
        return (await self._session.execute(stmt)).scalar_one()
