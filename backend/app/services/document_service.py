"""
Document service — business logic for document management.

Orchestrates:
  - File validation and storage (delegates to StorageService)
  - Database record creation and management (delegates to DocumentRepository)
  - Authorization (ensure users can only access their own documents)
  - Error handling and cleanup (delete file on DB write failure)

The upload sequence is designed to be safe against partial failures:
  1. Validate and save file to disk first
  2. Create the DB record second
  3. If DB creation fails → delete the file (compensating transaction)
  4. If file creation fails → never create the DB record (nothing to clean up)

This sequence means the filesystem is always the authoritative source for
whether a file exists. A DB record without a file is a bug; a file without
a DB record is cleaned up by a periodic janitor job (future Phase 5).
"""

import math
from typing import Optional
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DocumentNotFoundException,
    ForbiddenException,
    ValidationException,
)
from app.core.logging import get_logger
from app.db.models import Document, User
from app.db.repositories.document_repository import DocumentRepository
from app.schemas.document import DocumentListResponse, DocumentListParams, DocumentSummaryResponse
from app.services.storage_service import StorageService

logger = get_logger(__name__)


class DocumentService:
    """
    Orchestrates document upload, retrieval, and deletion.

    One instance per request — session and storage_service are injected.
    """

    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService,
    ) -> None:
        self._session = session
        self._repo = DocumentRepository(session)
        self._storage = storage_service

    # ── Upload ────────────────────────────────────────────────────────────────

    async def upload_document(
        self,
        *,
        upload: UploadFile,
        user: User,
    ) -> Document:
        """
        Process and persist an uploaded file.

        Steps:
          1. StorageService validates and writes the file to disk.
          2. DocumentRepository creates the DB record.
          3. On any DB failure, the file is deleted (compensating transaction).

        Raises:
          FileTooLargeException, UnsupportedFileTypeException,
          ValidationException — propagated from StorageService.
          Any SQLAlchemy exception — causes file cleanup then re-raise.

        Returns:
          The newly created Document ORM instance (status='pending').
        """
        user_id_str = str(user.id)

        if not upload.filename:
            raise ValidationException("No file was provided in the request.")

        # Step 1: validate and persist to disk
        storage_meta = await self._storage.save_upload(
            upload=upload,
            user_id=user_id_str,
        )

        # Step 2: create DB record — wrapped so we can clean up on failure
        try:
            document = await self._repo.create_document(
                user_id=user.id,
                original_filename=storage_meta["original_filename"],
                stored_filename=storage_meta["stored_filename"],
                file_type=storage_meta["file_type"],
                mime_type=storage_meta["mime_type"],
                file_size_bytes=storage_meta["file_size_bytes"],
                storage_path=storage_meta["storage_path"],
            )
        except Exception as db_exc:
            # Compensating transaction: remove the file we just saved
            logger.error(
                "document_db_create_failed_cleaning_up",
                user_id=user_id_str,
                storage_path=storage_meta["storage_path"],
                error=str(db_exc),
            )
            await self._storage.delete_file(storage_meta["storage_path"])
            raise

        logger.info(
            "document_uploaded",
            document_id=str(document.id),
            user_id=user_id_str,
            original_filename=storage_meta["original_filename"],
            file_type=storage_meta["file_type"],
            size_bytes=storage_meta["file_size_bytes"],
        )

        return document

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_document(
        self,
        *,
        document_id: UUID,
        user: User,
    ) -> Document:
        """
        Retrieve a document by ID, enforcing ownership.

        Raises:
          DocumentNotFoundException if the document does not exist
          OR does not belong to this user (same exception to prevent
          resource enumeration — callers cannot tell which case applies).
        """
        document = await self._repo.get_by_id_and_user(
            document_id=document_id,
            user_id=user.id,
        )
        if document is None:
            raise DocumentNotFoundException(document_id)
        return document

    async def list_documents(
        self,
        *,
        user: User,
        params: DocumentListParams,
    ) -> DocumentListResponse:
        """
        Return a paginated list of the user's documents.

        Applies optional status and file_type filters from query parameters.
        All results are scoped to the authenticated user.
        """
        documents, total = await self._repo.get_documents_by_user(
            user_id=user.id,
            page=params.page,
            limit=params.limit,
            status=params.status,
            file_type=params.file_type,
            sort_by=params.sort_by,
            sort_order=params.sort_order,
        )

        total_pages = math.ceil(total / params.limit) if total > 0 else 0

        return DocumentListResponse(
            items=[DocumentSummaryResponse.model_validate(doc) for doc in documents],
            total=total,
            page=params.page,
            limit=params.limit,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete_document(
        self,
        *,
        document_id: UUID,
        user: User,
    ) -> None:
        """
        Delete a document's physical file and its database record.

        Delete sequence:
          1. Load and authorize the document (raises if not found/authorized)
          2. Capture the storage_path before deletion (lost after ORM delete)
          3. Delete the DB record first (if this fails, file is untouched)
          4. Delete the physical file second (file system is eventually consistent)

        Why DB first?
          If file deletion fails (disk full, permissions), the DB record is
          already gone and the file becomes an orphan — cleaned up by a janitor.
          If we deleted the file first and then the DB write failed, we'd have
          a DB record pointing to a non-existent file, which is harder to detect.

        Raises:
          DocumentNotFoundException if the document doesn't exist or isn't owned
          by this user.
        """
        document = await self.get_document(document_id=document_id, user=user)
        storage_path = document.storage_path
        document_id_str = str(document.id)

        # Step 1: delete DB record (cascades to document_chunks in Phase 4)
        await self._repo.delete_document(document)

        # Step 2: delete physical file (best-effort — log but don't raise)
        deleted = await self._storage.delete_file(storage_path)
        if not deleted:
            logger.warning(
                "document_file_missing_on_delete",
                document_id=document_id_str,
                storage_path=storage_path,
            )

        logger.info(
            "document_deleted",
            document_id=document_id_str,
            user_id=str(user.id),
            storage_path=storage_path,
            file_deleted=deleted,
        )

    # ── Storage Stats (for plan tier enforcement — future) ───────────────────

    async def get_user_storage_stats(self, user: User) -> dict:
        """
        Return storage usage statistics for a user.
        Used for displaying storage quotas in the UI.
        """
        total_bytes = await self._repo.get_user_storage_bytes(user.id)
        doc_count = await self._repo.get_user_document_count(user.id)
        max_bytes = 1024 * 1024 * 1024  # 1 GB default quota (plan-based in future)

        return {
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
            "document_count": doc_count,
            "quota_bytes": max_bytes,
            "quota_mb": round(max_bytes / (1024 * 1024), 2),
            "usage_percent": round((total_bytes / max_bytes) * 100, 1) if max_bytes > 0 else 0,
        }
