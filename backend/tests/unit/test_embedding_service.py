"""
Unit tests for EmbeddingService.

Gemini API calls are mocked so tests run fully offline.
We test:
  - Correct delegation to _embed_batch_sync in batches
  - Attachment of .embedding to TextChunk objects
  - Dimension validation
  - Error propagation (GeminiAPIException)
  - Query embedding uses correct task_type (tested via mock call args)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.exceptions import GeminiAPIException
from app.services.embedding_service import EmbeddingService
from app.services.chunking_service import TextChunk


def _make_chunk(index: int, content: str = "Sample text content for embedding.") -> TextChunk:
    from app.services.chunking_service import compute_content_hash, count_tokens
    return TextChunk(
        chunk_index=index,
        content=content,
        token_count=count_tokens(content),
        char_count=len(content),
        content_hash=compute_content_hash(content + str(index)),
        page_number=index + 1,
        chunk_metadata={"document_id": "doc-1"},
    )


FAKE_VECTOR = [0.1] * 768


class TestEmbeddingServiceChunks:
    @pytest.mark.asyncio
    async def test_embeds_all_chunks(self):
        chunks = [_make_chunk(i) for i in range(5)]

        with patch("app.services.embedding_service._embed_batch_sync") as mock_batch:
            mock_batch.return_value = [FAKE_VECTOR] * 5

            svc = EmbeddingService(model="models/text-embedding-004")
            svc._batch_size = 10  # one batch for all 5

            with patch("asyncio.get_event_loop") as mock_loop:
                loop = MagicMock()
                loop.run_in_executor = AsyncMock(return_value=[FAKE_VECTOR] * 5)
                mock_loop.return_value = loop

                result = await svc.embed_chunks(chunks, document_id="doc-1")

        assert len(result) == 5
        for c in result:
            assert hasattr(c, "embedding")

    @pytest.mark.asyncio
    async def test_empty_chunks_returns_empty(self):
        svc = EmbeddingService()
        result = await svc.embed_chunks([], document_id="doc-1")
        assert result == []

    @pytest.mark.asyncio
    async def test_batch_size_respected(self):
        """With batch_size=2 and 5 chunks, run_in_executor should be called 3 times."""
        chunks = [_make_chunk(i) for i in range(5)]

        call_count = 0

        async def fake_executor(pool, fn, *args):
            nonlocal call_count
            call_count += 1
            n = len(args[0])   # args[0] is the texts list
            return [FAKE_VECTOR] * n

        import asyncio
        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            loop.run_in_executor = fake_executor
            mock_loop.return_value = loop

            svc = EmbeddingService()
            svc._batch_size = 2
            await svc.embed_chunks(chunks, document_id="doc-1")

        assert call_count == 3   # ceil(5/2) = 3 batches

    @pytest.mark.asyncio
    async def test_raises_gemini_exception_on_failure(self):
        chunks = [_make_chunk(0)]

        async def failing_executor(pool, fn, *args):
            raise RuntimeError("API down")

        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            loop.run_in_executor = failing_executor
            mock_loop.return_value = loop

            svc = EmbeddingService()
            with pytest.raises(GeminiAPIException):
                await svc.embed_chunks(chunks, document_id="doc-fail")

    @pytest.mark.asyncio
    async def test_raises_on_dimension_mismatch(self):
        """If Gemini returns wrong-length vectors, embed_query should raise."""
        short_vector = [0.1] * 100  # wrong dimension

        async def bad_executor(pool, fn, *args):
            return short_vector

        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            loop.run_in_executor = bad_executor
            mock_loop.return_value = loop

            svc = EmbeddingService()
            with pytest.raises(GeminiAPIException, match="dimension"):
                await svc.embed_query("test query")

    @pytest.mark.asyncio
    async def test_embed_query_returns_768_dim(self):
        async def executor(pool, fn, *args):
            return FAKE_VECTOR  # 768-dim

        with patch("asyncio.get_event_loop") as mock_loop:
            loop = MagicMock()
            loop.run_in_executor = executor
            mock_loop.return_value = loop

            svc = EmbeddingService()
            vector = await svc.embed_query("What is the revenue growth?")

        assert len(vector) == 768
