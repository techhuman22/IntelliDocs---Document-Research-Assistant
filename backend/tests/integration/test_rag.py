"""
Integration tests for the RAG API endpoints.

Tests use the FastAPI TestClient with dependency overrides to mock:
  - EmbeddingService.embed_query  →  returns a fixed 768-dim vector
  - VectorRepository.similarity_search  →  returns pre-built fake chunks
  - process_document Celery task  →  mocked to avoid real worker

These tests verify HTTP contracts (status codes, response schema, auth gating)
without making real Gemini API calls or hitting a real pgvector database.

Setup required for local run:
  - Postgres with pgvector (docker-compose up postgres)
  - Run Alembic migrations: alembic upgrade head
  - The tests create/delete their own data via fixtures.

Alternatively, the CI fixture in conftest.py can override get_db to use
a test database.
"""

import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.schemas.rag import RetrievedChunk


# ── Helpers ───────────────────────────────────────────────────────────────────

FAKE_VECTOR = [0.1] * 768

FAKE_CHUNK = RetrievedChunk(
    chunk_id=uuid4(),
    document_id=uuid4(),
    original_filename="test_document.pdf",
    chunk_index=0,
    content="This is a relevant passage about revenue growth in Q3.",
    similarity_score=0.92,
    page_number=5,
    chunk_metadata={"section": "Financial Summary"},
)


# ── Tests: trigger processing ─────────────────────────────────────────────────

@pytest.mark.asyncio
class TestTriggerProcessing:
    async def test_unauthenticated_returns_401(self, async_client: AsyncClient):
        response = await async_client.post(f"/api/v1/documents/process/{uuid4()}")
        assert response.status_code == 401

    async def test_document_not_found_returns_404(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        response = await async_client.post(
            f"/api/v1/documents/process/{uuid4()}",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_queues_pending_document(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        uploaded_document_id: str,
    ):
        with patch("app.workers.tasks.process_document.delay") as mock_delay:
            response = await async_client.post(
                f"/api/v1/documents/process/{uploaded_document_id}",
                headers=auth_headers,
            )
        assert response.status_code == 202
        data = response.json()
        assert data["status"] in ("processing", "ready")
        mock_delay.assert_called_once()

    async def test_already_ready_skips_queue(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        ready_document_id: str,
    ):
        with patch("app.workers.tasks.process_document.delay") as mock_delay:
            response = await async_client.post(
                f"/api/v1/documents/process/{ready_document_id}",
                headers=auth_headers,
            )
        assert response.status_code == 202
        assert response.json()["status"] == "ready"
        mock_delay.assert_not_called()

    async def test_force_requeries_ready_document(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        ready_document_id: str,
    ):
        with patch("app.workers.tasks.process_document.delay") as mock_delay:
            response = await async_client.post(
                f"/api/v1/documents/process/{ready_document_id}?force=true",
                headers=auth_headers,
            )
        assert response.status_code == 202
        mock_delay.assert_called_once()


# ── Tests: chunk listing ──────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestListChunks:
    async def test_unauthenticated_returns_401(self, async_client: AsyncClient):
        response = await async_client.get(f"/api/v1/documents/{uuid4()}/chunks")
        assert response.status_code == 401

    async def test_not_ready_document_returns_422(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        uploaded_document_id: str,  # status='pending'
    ):
        response = await async_client.get(
            f"/api/v1/documents/{uploaded_document_id}/chunks",
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_returns_chunk_list(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        ready_document_id: str,
    ):
        response = await async_client.get(
            f"/api/v1/documents/{ready_document_id}/chunks",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "chunks" in data
        assert "total_chunks" in data
        assert isinstance(data["chunks"], list)

    async def test_pagination_params_respected(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
        ready_document_id: str,
    ):
        response = await async_client.get(
            f"/api/v1/documents/{ready_document_id}/chunks?page=1&limit=5",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["chunks"]) <= 5
        assert data["limit"] == 5
        assert data["page"] == 1


# ── Tests: similarity search ──────────────────────────────────────────────────

@pytest.mark.asyncio
class TestRetrievalSearch:
    async def test_unauthenticated_returns_401(self, async_client: AsyncClient):
        response = await async_client.post(
            "/api/v1/retrieval/search",
            json={"query": "test"},
        )
        assert response.status_code == 401

    async def test_empty_query_rejected(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        response = await async_client.post(
            "/api/v1/retrieval/search",
            json={"query": ""},
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_returns_search_response_schema(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        """Mock embedding + search so we don't need real Gemini or pgvector."""
        with (
            patch(
                "app.services.retrieval_service.RetrievalService.search",
                new_callable=AsyncMock,
                return_value=([FAKE_CHUNK], {"total_latency_ms": 42}),
            ),
        ):
            response = await async_client.post(
                "/api/v1/retrieval/search",
                json={
                    "query": "What is the revenue growth?",
                    "top_k": 5,
                    "similarity_threshold": 0.7,
                },
                headers=auth_headers,
            )

        assert response.status_code == 200
        data = response.json()
        assert data["query"] == "What is the revenue growth?"
        assert "chunks" in data
        assert "context" in data
        assert "citations" in data
        assert isinstance(data["chunks"], list)

    async def test_top_k_validation(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        response = await async_client.post(
            "/api/v1/retrieval/search",
            json={"query": "test", "top_k": 99},   # exceeds max=20
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_similarity_threshold_validation(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        response = await async_client.post(
            "/api/v1/retrieval/search",
            json={"query": "test", "similarity_threshold": 1.5},   # exceeds max=1.0
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_exclude_metadata_strips_chunk_metadata(
        self,
        async_client: AsyncClient,
        auth_headers: dict,
    ):
        with (
            patch(
                "app.services.retrieval_service.RetrievalService.search",
                new_callable=AsyncMock,
                return_value=([FAKE_CHUNK], {}),
            ),
        ):
            response = await async_client.post(
                "/api/v1/retrieval/search",
                json={"query": "test", "include_metadata": False},
                headers=auth_headers,
            )

        assert response.status_code == 200
        for chunk in response.json()["chunks"]:
            assert chunk["chunk_metadata"] == {}
