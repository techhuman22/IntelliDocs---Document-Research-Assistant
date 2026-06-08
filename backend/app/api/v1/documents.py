"""
Document management route handlers.

All routes require authentication. Users can only access their own documents.

Endpoints:
  POST   /api/v1/documents/upload              — upload a new document
  POST   /api/v1/documents/process/{id}        — trigger processing for a document
  GET    /api/v1/documents                     — list user's documents (paginated)
  GET    /api/v1/documents/{document_id}       — get document details
  DELETE /api/v1/documents/{document_id}       — delete document + file
  GET    /api/v1/documents/storage/stats       — storage usage summary
"""

from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_active_user, get_document_service
from app.db.base import get_db
from app.db.models import User
from app.schemas.auth import MessageResponse
from app.schemas.document import (
    DocumentListParams,
    DocumentListResponse,
    DocumentResponse,
    UploadResponse,
)
from app.services.document_service import DocumentService

router = APIRouter()


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a new document",
    responses={
        201: {"description": "File uploaded and queued for processing."},
        400: {"description": "No file provided or empty file."},
        401: {"description": "Authentication required."},
        413: {"description": "File exceeds the maximum allowed size."},
        415: {"description": "File type is not supported (PDF, DOCX, TXT only)."},
        422: {"description": "Validation failed."},
    },
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(
        ...,
        description="Document file to upload. Supported types: PDF, DOCX, TXT. Max size: 50 MB.",
    ),
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
    db: AsyncSession = Depends(get_db),
) -> UploadResponse:
    """
    Upload a document file for processing.

    **Supported formats:** PDF, DOCX, TXT
    **Maximum size:** 50 MB (configurable via `MAX_UPLOAD_SIZE_MB` env var)

    Automatically starts chunking + embedding in the background after upload.
    Poll the document's status endpoint until it transitions to `ready`.
    """
    document = await document_service.upload_document(
        upload=file,
        user=current_user,
    )

    # Explicitly commit so the background task (which opens its own connection)
    # can see the new document row. Otherwise the auto-commit happens only after
    # the response is sent, racing with the background task.
    await db.commit()

    # Auto-trigger processing after upload. Runs after response is sent.
    doc_id = str(document.id)
    user_id = str(current_user.id)

    async def _safe_process():
        from app.workers.tasks import run_document_processing_inline
        from app.core.logging import get_logger
        _log = get_logger(__name__)
        try:
            await run_document_processing_inline(doc_id, user_id)
        except Exception as exc:
            _log.error("auto_processing_failed", document_id=doc_id, error=str(exc))

    background_tasks.add_task(_safe_process)

    return UploadResponse(
        document_id=document.id,
        original_filename=document.original_filename,
        file_type=document.file_type,
        file_size_bytes=document.file_size_bytes,
        status=document.status,
    )


# ── List Documents ────────────────────────────────────────────────────────────

@router.get(
    "",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all documents for the authenticated user",
    responses={
        200: {"description": "Paginated list of documents."},
        401: {"description": "Authentication required."},
    },
)
async def list_documents(
    page: int = Query(default=1, ge=1, description="Page number (1-based)."),
    limit: int = Query(default=20, ge=1, le=100, description="Items per page (max 100)."),
    status_filter: str = Query(
        default=None,
        alias="status",
        description="Filter by status: pending | processing | ready | failed",
    ),
    file_type: str = Query(
        default=None,
        description="Filter by file type: pdf | docx | txt",
    ),
    sort_by: str = Query(
        default="created_at",
        description="Sort field: created_at | original_filename | file_size_bytes",
    ),
    sort_order: str = Query(
        default="desc",
        description="Sort direction: asc | desc",
    ),
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentListResponse:
    """
    Retrieve a paginated list of all documents belonging to the authenticated user.

    Results are always scoped to the current user — no cross-user access.

    **Sorting:** `created_at` (default, newest first), `original_filename`, `file_size_bytes`

    **Filtering:** `status` and `file_type` query parameters can be combined.
    """
    params = DocumentListParams(
        page=page,
        limit=limit,
        status=status_filter,
        file_type=file_type,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return await document_service.list_documents(user=current_user, params=params)


# ── Trigger Processing — must come BEFORE /{document_id} to avoid route conflict ──

@router.post(
    "/process/{document_id}",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger document processing (chunking + embedding)",
    responses={
        202: {"description": "Processing started."},
        401: {"description": "Authentication required."},
        404: {"description": "Document not found."},
    },
)
async def trigger_processing(
    document_id: UUID,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False, description="Re-process even if already ready."),
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
) -> dict:
    """
    Start the chunking + embedding pipeline for a document.
    Runs inline (no Celery needed) as a FastAPI background task.
    """
    # Verify document belongs to this user
    document = await document_service.get_document(
        document_id=document_id,
        user=current_user,
    )

    doc_id = str(document_id)
    user_id = str(current_user.id)

    async def _safe_process():
        import asyncio
        from app.workers.tasks import run_document_processing_inline
        from app.core.logging import get_logger
        _log = get_logger(__name__)
        try:
            await asyncio.sleep(0.3)
            await run_document_processing_inline(doc_id, user_id)
        except Exception as exc:
            _log.error("manual_processing_failed", document_id=doc_id, error=str(exc))

    background_tasks.add_task(_safe_process)

    return {
        "document_id": doc_id,
        "status": "processing",
        "message": "Processing started. Refresh the document list to see the updated status.",
    }


# ── Storage Stats — must come BEFORE /{document_id} to avoid route conflict ──

@router.get(
    "/storage/stats",
    status_code=status.HTTP_200_OK,
    summary="Get storage usage statistics for the authenticated user",
    responses={
        200: {"description": "Storage usage summary."},
        401: {"description": "Authentication required."},
    },
)
async def get_storage_stats(
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
) -> dict:
    """
    Return the authenticated user's storage usage:
    - Total bytes and MB consumed
    - Document count
    - Quota usage percentage (1 GB default)
    """
    return await document_service.get_user_storage_stats(current_user)


# ── Get Single Document ───────────────────────────────────────────────────────

@router.get(
    "/{document_id}",
    response_model=DocumentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details for a specific document",
    responses={
        200: {"description": "Document details returned."},
        401: {"description": "Authentication required."},
        404: {"description": "Document not found or does not belong to the authenticated user."},
    },
)
async def get_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
) -> DocumentResponse:
    """
    Retrieve the full details of a specific document.

    Returns HTTP 404 if the document does not exist **or** if it belongs
    to a different user — both cases are indistinguishable to the client
    to prevent resource enumeration.
    """
    document = await document_service.get_document(
        document_id=document_id,
        user=current_user,
    )
    return DocumentResponse.model_validate(document)


# ── Delete Document ───────────────────────────────────────────────────────────

@router.delete(
    "/{document_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a document and its physical file",
    responses={
        200: {"description": "Document and file deleted successfully."},
        401: {"description": "Authentication required."},
        404: {"description": "Document not found or does not belong to the authenticated user."},
    },
)
async def delete_document(
    document_id: UUID,
    current_user: User = Depends(get_current_active_user),
    document_service: DocumentService = Depends(get_document_service),
) -> MessageResponse:
    """
    Permanently delete a document.

    This action:
    - Removes the database record (and all associated chunks, logs via CASCADE)
    - Deletes the physical file from disk

    **This action is irreversible.** If the document is currently being processed,
    deletion will still succeed — the background worker will fail gracefully
    when it cannot find the document record.
    """
    await document_service.delete_document(
        document_id=document_id,
        user=current_user,
    )
    return MessageResponse(message=f"Document {document_id} deleted successfully.")
