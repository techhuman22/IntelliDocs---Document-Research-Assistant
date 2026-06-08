"""
Document repository — all database operations for the documents table.

Follows the same Repository pattern established in Phase 2.
Service layer calls these methods; route handlers call service methods.
No HTTP or business logic here — pure data access.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document
from app.db.repositories.base import BaseRepository


# Sort column mapping — prevents SQL injection via sort_by param
_SORTABLE_COLUMNS: dict[str, any] = {
    "created_at":       Document.created_at,
    "original_filename": Document.original_filename,
    "file_size_bytes":  Document.file_size_bytes,
}


class DocumentRepository(BaseRepository[Document]):
    """Data access layer for the documents table."""

    model = Document

    # ── Read ──────────────────────────────────────────────────────────────────

    async def get_by_id(self, document_id: UUID) -> Optional[Document]:
        """Fetch a document by its primary key. Returns None if not found."""
        return await self._session.get(Document, document_id)

    async def get_by_id_and_user(
        self,
        document_id: UUID,
        user_id: UUID,
    ) -> Optional[Document]:
        """
        Fetch a document that belongs to a specific user.

        Always filters by both document_id AND user_id. This prevents
        horizontal privilege escalation — a user cannot access another
        user's document even if they know its UUID.
        """
        result = await self._session.execute(
            select(Document).where(
                Document.id == document_id,
                Document.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_documents_by_user(
        self,
        user_id: UUID,
        *,
        page: int = 1,
        limit: int = 20,
        status: Optional[str] = None,
        file_type: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[Document], int]:
        """
        Paginated list of documents for a user with optional filtering.

        Returns a tuple of (documents, total_count).
        total_count is computed in a separate COUNT query so pagination
        metadata is accurate.

        Args:
            user_id:    Filter to this user's documents only.
            page:       1-based page number.
            limit:      Items per page.
            status:     Optional filter: 'pending'|'processing'|'ready'|'failed'.
            file_type:  Optional filter: 'pdf'|'docx'|'txt'.
            sort_by:    Column name to sort by (validated against allowlist).
            sort_order: 'asc' or 'desc'.
        """
        # Base filter — always scope to the authenticated user
        base_filter = [Document.user_id == user_id]

        if status:
            base_filter.append(Document.status == status)
        if file_type:
            base_filter.append(Document.file_type == file_type)

        # Resolve sort column from allowlist (prevents SQL injection)
        sort_col = _SORTABLE_COLUMNS.get(sort_by, Document.created_at)
        order_fn = desc if sort_order == "desc" else asc
        order_clause = order_fn(sort_col)

        # COUNT query — reuses same filters, no LIMIT/OFFSET
        count_stmt = select(func.count()).select_from(Document).where(*base_filter)
        total_result = await self._session.execute(count_stmt)
        total: int = total_result.scalar_one()

        # Data query
        offset = (page - 1) * limit
        data_stmt = (
            select(Document)
            .where(*base_filter)
            .order_by(order_clause)
            .offset(offset)
            .limit(limit)
        )
        data_result = await self._session.execute(data_stmt)
        documents = list(data_result.scalars().all())

        return documents, total

    async def get_user_document_count(self, user_id: UUID) -> int:
        """Return the total number of documents owned by a user."""
        result = await self._session.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.user_id == user_id)
        )
        return result.scalar_one()

    async def get_user_storage_bytes(self, user_id: UUID) -> int:
        """
        Return the total bytes stored across all of a user's documents.
        Used to enforce per-user storage quotas (future feature).
        """
        result = await self._session.execute(
            select(func.coalesce(func.sum(Document.file_size_bytes), 0))
            .where(Document.user_id == user_id)
        )
        return result.scalar_one()

    # ── Write ─────────────────────────────────────────────────────────────────

    async def create_document(
        self,
        *,
        user_id: UUID,
        original_filename: str,
        stored_filename: str,
        file_type: str,
        mime_type: str,
        file_size_bytes: int,
        storage_path: str,
    ) -> Document:
        """
        Persist a new document record immediately after the file is saved to disk.

        The document is created with status='pending'. The background worker
        (Phase 4) will transition it to 'processing' → 'ready' | 'failed'.
        """
        return await self.create(
            user_id=user_id,
            original_filename=original_filename,
            stored_filename=stored_filename,
            file_name=original_filename,   # backward-compat alias
            file_type=file_type,
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            storage_path=storage_path,
            status="pending",
            chunk_count=0,
            doc_metadata={},
        )

    async def update_status(
        self,
        document: Document,
        status: str,
        error_message: Optional[str] = None,
    ) -> Document:
        """
        Transition a document to a new pipeline status.
        Called by the background worker (Phase 4).
        """
        updates: dict = {"status": status}
        if error_message is not None:
            updates["error_message"] = error_message
        return await self.update(document, **updates)

    async def update_processing_results(
        self,
        document: Document,
        *,
        page_count: Optional[int] = None,
        word_count: Optional[int] = None,
        chunk_count: int = 0,
        doc_metadata: Optional[dict] = None,
    ) -> Document:
        """
        Store the results of document text extraction.
        Called by the background worker after parsing is complete.
        """
        updates: dict = {
            "status": "ready",
            "chunk_count": chunk_count,
        }
        if page_count is not None:
            updates["page_count"] = page_count
        if word_count is not None:
            updates["word_count"] = word_count
        if doc_metadata is not None:
            updates["doc_metadata"] = doc_metadata
        return await self.update(document, **updates)

    async def delete_document(self, document: Document) -> None:
        """
        Hard-delete the document DB record.
        The physical file must be deleted by the caller (StorageService)
        BEFORE calling this — the storage_path is on the ORM object
        and would be inaccessible after deletion.
        """
        await self.delete(document)
