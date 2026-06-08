"""
Integration tests for the document management API.

Tests cover the full HTTP layer. File I/O and Redis are mocked.
The database uses the rolled-back test session from conftest.py.
"""

import io
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

# ── Helpers ───────────────────────────────────────────────────────────────────

REGISTER_PAYLOAD = {
    "full_name": "Test User",
    "email": "testdocs@example.com",
    "password": "MyStr0ng!Pass",
}

LOGIN_PAYLOAD = {
    "email": "testdocs@example.com",
    "password": "MyStr0ng!Pass",
}


def _mock_redis():
    mock = AsyncMock()
    mock.setex = AsyncMock(return_value=True)
    mock.delete = AsyncMock(return_value=1)
    mock.get = AsyncMock(return_value=None)
    mock.aclose = AsyncMock()
    return mock


def _make_pdf_file(content: bytes = b"%PDF-1.7 fake pdf content") -> tuple:
    """Return (filename, file_bytes, content_type) for a fake PDF."""
    return ("test.pdf", content, "application/pdf")


def _make_txt_file(content: bytes = b"Hello, this is plain text.") -> tuple:
    return ("notes.txt", content, "text/plain")


def _make_docx_file() -> tuple:
    # DOCX is a ZIP file — magic bytes PK\x03\x04
    content = b"PK\x03\x04" + b"\x00" * 100
    return ("document.docx", content, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


async def _get_auth_token(client: AsyncClient) -> str:
    """Register + login and return the access token."""
    with patch("app.api.dependencies.get_redis") as mock_get_redis:
        mock_get_redis.return_value = _mock_redis()
        await client.post("/api/v1/auth/register", json=REGISTER_PAYLOAD)
        login_resp = await client.post("/api/v1/auth/login", json=LOGIN_PAYLOAD)
    return login_resp.json()["tokens"]["access_token"]


# ── Upload Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_pdf_success(client: AsyncClient):
    token = await _get_auth_token(client)
    filename, content, ct = _make_pdf_file()

    with patch("app.services.storage_service.StorageService.save_upload", new_callable=AsyncMock) as mock_save:
        mock_save.return_value = {
            "original_filename": filename,
            "stored_filename": f"abc123-{filename}",
            "storage_path": f"/uploads/user/{filename}",
            "file_type": "pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": len(content),
        }

        response = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (filename, io.BytesIO(content), ct)},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == "test.pdf"
    assert data["file_type"] == "pdf"
    assert data["status"] == "pending"
    assert "document_id" in data


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    filename, content, ct = _make_pdf_file()
    response = await client.post(
        "/api/v1/documents/upload",
        files={"file": (filename, io.BytesIO(content), ct)},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_upload_rejects_image(client: AsyncClient):
    token = await _get_auth_token(client)
    response = await client.post(
        "/api/v1/documents/upload",
        headers={"Authorization": f"Bearer {token}"},
        files={"file": ("photo.jpg", io.BytesIO(b"\xff\xd8\xff fake jpg"), "image/jpeg")},
    )
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


@pytest.mark.asyncio
async def test_upload_rejects_empty_file(client: AsyncClient):
    token = await _get_auth_token(client)

    with patch("app.services.storage_service.StorageService.save_upload", new_callable=AsyncMock) as mock_save:
        from app.core.exceptions import ValidationException
        mock_save.side_effect = ValidationException("Uploaded file is empty.")

        response = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("empty.pdf", io.BytesIO(b""), "application/pdf")},
        )

    assert response.status_code == 422


# ── List Tests ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_documents_empty(client: AsyncClient):
    token = await _get_auth_token(client)
    response = await client.get(
        "/api/v1/documents",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_documents_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/documents")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_documents_pagination_params(client: AsyncClient):
    token = await _get_auth_token(client)
    response = await client.get(
        "/api/v1/documents?page=2&limit=5",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["page"] == 2
    assert data["limit"] == 5


@pytest.mark.asyncio
async def test_list_documents_invalid_page_rejected(client: AsyncClient):
    token = await _get_auth_token(client)
    response = await client.get(
        "/api/v1/documents?page=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# ── Get Single Document Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_nonexistent_document_returns_404(client: AsyncClient):
    token = await _get_auth_token(client)
    fake_id = str(uuid4())
    response = await client.get(
        f"/api/v1/documents/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_document_requires_auth(client: AsyncClient):
    response = await client.get(f"/api/v1/documents/{uuid4()}")
    assert response.status_code == 401


# ── Delete Tests ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_nonexistent_document_returns_404(client: AsyncClient):
    token = await _get_auth_token(client)
    fake_id = str(uuid4())
    response = await client.delete(
        f"/api/v1/documents/{fake_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_document_requires_auth(client: AsyncClient):
    response = await client.delete(f"/api/v1/documents/{uuid4()}")
    assert response.status_code == 401


# ── Storage Stats Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_storage_stats(client: AsyncClient):
    token = await _get_auth_token(client)
    response = await client.get(
        "/api/v1/documents/storage/stats",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "total_bytes" in data
    assert "document_count" in data
    assert "usage_percent" in data
    assert data["document_count"] == 0
    assert data["total_bytes"] == 0


# ── Full Upload + Get + Delete Lifecycle ──────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_then_get_then_delete(client: AsyncClient):
    """End-to-end lifecycle: upload → list → get → delete → confirm gone."""
    token = await _get_auth_token(client)
    filename, content, ct = _make_pdf_file()

    # Upload
    with patch("app.services.storage_service.StorageService.save_upload", new_callable=AsyncMock) as mock_save, \
         patch("app.services.storage_service.StorageService.delete_file", new_callable=AsyncMock) as mock_delete:

        mock_save.return_value = {
            "original_filename": filename,
            "stored_filename": "abc123-test.pdf",
            "storage_path": "/tmp/test.pdf",
            "file_type": "pdf",
            "mime_type": "application/pdf",
            "file_size_bytes": len(content),
        }
        mock_delete.return_value = True

        upload_resp = await client.post(
            "/api/v1/documents/upload",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (filename, io.BytesIO(content), ct)},
        )
        assert upload_resp.status_code == 201
        doc_id = upload_resp.json()["document_id"]

        # Get
        get_resp = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == doc_id

        # List shows 1 document
        list_resp = await client.get(
            "/api/v1/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert list_resp.json()["total"] == 1

        # Delete
        del_resp = await client.delete(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert del_resp.status_code == 200

        # Confirm gone
        get_after_del = await client.get(
            f"/api/v1/documents/{doc_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert get_after_del.status_code == 404
