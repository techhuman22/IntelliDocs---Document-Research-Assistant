"""
Embedding service — converts text chunks into 384-dimensional vectors using
sentence-transformers/all-MiniLM-L6-v2 running locally via HuggingFaceEmbeddings.

Why all-MiniLM-L6-v2?
  - Only ~80 MB vs ~420 MB for all-mpnet-base-v2 — fits in Render free tier (512 MB RAM).
  - Produces 384-dim vectors — half the size, faster cosine similarity.
  - Still excellent retrieval quality (MiniLM is the go-to lightweight model).

Lazy loading:
  The model is loaded on first use, NOT at import/module level.  This avoids
  holding ~200 MB of RAM during startup when other init (DB, Redis) is also
  allocating memory, which caused OOM (exit code 137) on Render free tier.

Threading:
  sentence-transformers is synchronous (PyTorch under the hood).
  We call it in a thread executor to avoid blocking the async event loop.
  The model object is initialised once (expensive) and reused for every call (cheap).

Batch processing:
  encode() accepts a list of strings and processes them in one forward
  pass — much faster than one-by-one. We still split into batches of
  EMBEDDING_BATCH_SIZE (64) to manage memory on machines with small RAM.
"""

import asyncio
import threading
from typing import Optional

from app.config.settings import settings
from app.core.logging import get_logger
from app.services.chunking_service import TextChunk

logger = get_logger(__name__)

# ── Lazy-loaded singleton model ───────────────────────────────────────────────
# The model is NOT loaded at import time.  Instead it is initialised on the
# first call to _get_model().  A threading.Lock ensures only one thread does
# the expensive load even if multiple requests arrive simultaneously.

_embedding_model = None
_model_lock = threading.Lock()


def _get_model():
    """Return the singleton HuggingFaceEmbeddings instance, loading on first call."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    with _model_lock:
        # Double-check after acquiring the lock
        if _embedding_model is not None:
            return _embedding_model

        logger.info(
            "embedding_model_loading",
            model=settings.EMBEDDING_MODEL_NAME,
            dimension=settings.EMBEDDING_DIMENSION,
        )

        from langchain_huggingface import HuggingFaceEmbeddings

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
        return _embedding_model


# ── Pure sync helpers — run inside thread executor ────────────────────────────

def _embed_texts_sync(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts synchronously (called in executor)."""
    return _get_model().embed_documents(texts)


def _embed_query_sync(query: str) -> list[float]:
    """Embed a single query string synchronously (called in executor)."""
    return _get_model().embed_query(query)


# ── Async service ─────────────────────────────────────────────────────────────

class EmbeddingService:
    """
    Generates embeddings for text chunks and queries via local sentence-transformers.

    Public interface:
      embed_chunks(chunks, document_id) -> list[TextChunk]  (chunks with .embedding set)
      embed_query(query)                -> list[float]       (384-dim normalised vector)
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
            Same list with each chunk.embedding set to a 384-dim float list.
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
        Embed a retrieval query into a 384-dim normalised vector.

        Args:
            query: Natural language search string.

        Returns:
            384-dimensional float vector (L2-normalised).
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
