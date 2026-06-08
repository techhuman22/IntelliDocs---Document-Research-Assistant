"""
Document Pydantic v2 schemas.

Response schemas are the only public surface of the document data model.
They are used in route return types and OpenAPI documentation.
No request body schema is needed for upload — the file comes via multipart form-data.
"""

from datetime import datetime
from typing import Any, Literal, Optional
from uuid import UUID

from pydantic import Field, computed_field

from app.schemas.base import BaseRequest, BaseResponse, PaginatedResponse


# ── Upload Status Literal ──────────────────────────────────────────────────────

DocumentStatus = Literal["pending", "processing", "ready", "failed"]
DocumentFileType = Literal["pdf", "docx", "txt"]


# ── Core Document Response ─────────────────────────────────────────────────────

class DocumentResponse(BaseResponse):
    """
    Full document representation returned by all document endpoints.

    Never includes storage_path (internal implementation detail) or
    the stored_filename (security — clients don't need the on-disk name).
    """

    id: UUID
    user_id: UUID
    original_filename: str = Field(description="The filename the user uploaded.")
    file_type: DocumentFileType
    mime_type: str
    file_size_bytes: int
    status: DocumentStatus
    error_message: Optional[str] = None
    page_count: Optional[int] = None
    word_count: Optional[int] = None
    chunk_count: int
    doc_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[misc]
    @property
    def file_size_mb(self) -> float:
        """Human-readable file size in megabytes, rounded to 2 decimal places."""
        return round(self.file_size_bytes / (1024 * 1024), 2)

    @computed_field  # type: ignore[misc]
    @property
    def is_ready(self) -> bool:
        """True when the document has been fully processed and is queryable."""
        return self.status == "ready"


class DocumentSummaryResponse(BaseResponse):
    """
    Lightweight document representation for list views.
    Omits heavy fields like doc_metadata to reduce payload size.
    """

    id: UUID
    original_filename: str
    file_type: DocumentFileType
    file_size_bytes: int
    status: DocumentStatus
    chunk_count: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[misc]
    @property
    def file_size_mb(self) -> float:
        return round(self.file_size_bytes / (1024 * 1024), 2)


# ── Upload Response ───────────────────────────────────────────────────────────

class UploadResponse(BaseResponse):
    """
    Immediate response after a file upload request.

    The document is created with status='pending' because the actual
    processing (text extraction, chunking, embedding) happens asynchronously
    in a background Celery worker (Phase 4).

    Clients should poll GET /documents/{id} or listen to SSE status events
    until status transitions to 'ready' or 'failed'.
    """

    document_id: UUID
    original_filename: str
    file_type: str
    file_size_bytes: int
    status: DocumentStatus
    message: str = "File uploaded successfully. Processing will begin shortly."

    model_config = {"from_attributes": True}


# ── List Response ─────────────────────────────────────────────────────────────

class DocumentListResponse(BaseResponse):
    """Paginated list of documents belonging to the authenticated user."""

    items: list[DocumentSummaryResponse]
    total: int
    page: int
    limit: int
    total_pages: int
    has_next: bool
    has_prev: bool

    model_config = {"from_attributes": True}


# ── Query Parameters ──────────────────────────────────────────────────────────

class DocumentListParams(BaseRequest):
    """
    Query parameters for GET /documents.
    Used for validation of query params via Depends(DocumentListParams).
    """

    page: int = Field(default=1, ge=1, description="Page number (1-based).")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page (max 100).")
    status: Optional[DocumentStatus] = Field(
        default=None,
        description="Filter by processing status.",
    )
    file_type: Optional[DocumentFileType] = Field(
        default=None,
        description="Filter by file type.",
    )
    sort_by: Literal["created_at", "original_filename", "file_size_bytes"] = Field(
        default="created_at",
        description="Field to sort by.",
    )
    sort_order: Literal["asc", "desc"] = Field(
        default="desc",
        description="Sort direction.",
    )

    # Override — query params are not request bodies, so extra=ignore is correct
    model_config = {"extra": "ignore"}
