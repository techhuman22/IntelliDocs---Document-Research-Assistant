"""
Embedding service — converts text chunks into 768-dimensional vectors using
sentence-transformers/all-mpnet-base-v2 running locally via HuggingFaceEmbeddings.

Why local embeddings?
  - No API key required, no rate limits, no per-token cost.
  - all-mpnet-base-v2 produces 768-dim vectors — matches the existing
    pgvector column (Vector(768)) exactly; no migration needed.
  - The model is downloaded once to ~/.cache/huggingface on first run
    and cached on disk for all subsequent calls.

Threading:
  sentence-transformers is synchronous (PyTorch under the hood).
  We call it in a thread executor to avoid blocking the async event loop.
  The model object is initialised once at module import (expensive) and
  reused for every call (cheap).

Batch processing:
  encode() accepts a list of strings and processes them in one forward
  pass — much faster than one-by-one. We still split into batches of
  EMBEDDING_BATCH_SIZE (64) to manage memory on machines with small RAM.
"""

import asyncio
from typing import Optional

from langchain_huggingface import HuggingFaceEmbeddings

from app.config.settings import settings
from app.core.logging import get_logger
from app.services.chunking_service import TextChunk

logger = get_logger(__name__)

# ── Singleton model — loaded once at startup ──────────────────────────────────
# HuggingFaceEmbeddings wraps sentence-transformers with a LangChain interface.
# model_kwargs={"device": "cpu"} is explicit — change to "cuda" if GPU is available.
# encode_kwargs={"normalize_embeddings": True} makes cosine similarity == dot product,
# which is what pgvector's <=> operator computes.
_embedding_model = HuggingFaceEmbeddings(
    model_name=settings.EMBEDDING_MODEL_NAME,
    model_kwargs={"device": "cpu"},
    encode_kwargs={"normalize_embeddings": True},
)

logger.info(
    "embedding_model_loaded",
    model=settings.EMBEDDING_MODEL_NAME,
    dimension=settings.EMBEDDING_DIMENSION,
)


# ── Pure sync helpers — run inside thread executor ────────────────────────────

def _embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts synchronously (called in executor)."""
    return _embedding_model.embed_documents(texts)


def _embed_query_sync(query: str) -> list[float]:
    """Embed a single query string synchronously (called in executor)."""
    return _embedding_model.embed_query(query)


# ── Async service ─────────────────────────────────────────────────────────────

class EmbeddingService:
    """
    Generates embeddings for text chunks and queries via local sentence-transformers.

    Public interface:
      embed_chunks(chunks, document_id) -> list[TextChunk]  (chunks with .embedding set)
      embed_query(query)                -> list[float]       (768-dim normalised vector)
    """

    def __init__(self) -> None:
        self._batch_size = settings.EMBEDDING_BATCH_SIZE
        logger.info(
            "embedding_service_init",
            model=settings.EMBEDDING_MODEL_NAME,
            batch_size=self._batch_size,
        )

    async def embed_chunks(
        self,
        chunks: list[TextChunk],
        document_id: str,
    ) -> list[TextChunk]:
        """
        Generate embeddings for all chunks and attach them to each TextChunk.

        Args:
            chunks:       Output of ChunkingService.split().
            document_id:  For structured logging.

        Returns:
            Same list with each chunk.embedding set to a 768-dim float list.
        """
        if not chunks:
            return chunks

        logger.info(
            "embedding_chunks_start",
            document_id=document_id,
            chunk_count=len(chunks),
            batch_size=self._batch_size,
        )

        loop = asyncio.get_event_loop()
        batches = [
            chunks[i : i + self._batch_size]
            for i in range(0, len(chunks), self._batch_size)
        ]

        embedded = 0
        for batch_idx, batch in enumerate(batches):
            texts = [c.content for c in batch]

            try:
                vectors: list[list[float]] = await loop.run_in_executor(
                    None,
                    _embed_texts_sync,
                    texts,
                )
            except Exception as exc:
                logger.error(
                    "embedding_batch_failed",
                    document_id=document_id,
                    batch_index=batch_idx,
                    error=str(exc),
                )
                raise RuntimeError(
                    f"Embedding batch {batch_idx} failed: {exc}"
                ) from exc

            for chunk, vector in zip(batch, vectors):
                chunk.embedding = vector  # type: ignore[attr-defined]
                embedded += 1

            logger.debug(
                "embedding_batch_done",
                document_id=document_id,
                batch_index=batch_idx,
                total_embedded=embedded,
            )

        logger.info(
            "embedding_chunks_complete",
            document_id=document_id,
            total_embedded=embedded,
        )
        return chunks

    async def embed_query(self, query: str) -> list[float]:
        """
        Embed a retrieval query into a 768-dim normalised vector.

        Args:
            query: Natural language search string.

        Returns:
            768-dimensional float vector (L2-normalised).
        """
        logger.debug("embedding_query", query_len=len(query))
        loop = asyncio.get_event_loop()

        try:
            vector: list[float] = await loop.run_in_executor(
                None,
                _embed_query_sync,
                query,
            )
        except Exception as exc:
            logger.error("query_embedding_failed", error=str(exc))
            raise RuntimeError(f"Query embedding failed: {exc}") from exc

        return vector
