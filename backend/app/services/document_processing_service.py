"""
Document processing service — orchestrates the full RAG indexing pipeline.

Pipeline order:
  1. Mark document status = 'processing'
  2. Parse raw file → ParsedDocument (text extraction)
  3. Chunk ParsedDocument → list[TextChunk]
  4. Embed TextChunk list → attach .embedding to each chunk
  5. Delete any pre-existing chunks (idempotent re-processing)
  6. Store chunks in document_chunks (bulk INSERT)
  7. Mark document status = 'ready', store chunk_count, page_count, word_count

Error handling:
  Any exception in steps 2–6 marks the document as 'failed' with an
  error_message. This lets users see WHY their document failed from the
  document list API, instead of a silent pending state.
  The exception is re-raised so the Celery task can log it at the worker level.

Idempotency:
  If the document is already 'ready', we skip re-processing by default.
  Pass force=True to re-index (e.g. after a settings change).
  The DELETE + INSERT in steps 5–6 ensures the chunk table stays consistent
  even if a previous processing attempt partially succeeded.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DocumentNotFoundException, DocumentProcessingException
from app.core.logging import get_logger
from app.db.repositories.document_repository import DocumentRepository
from app.db.repositories.vector_repository import VectorRepository
from app.services.chunking_service import ChunkingService
from app.services.document_parser_service import DocumentParserService
from app.services.embedding_service import EmbeddingService
from app.services.storage_service import StorageService

logger = get_logger(__name__)


class DocumentProcessingService:
    """
    Orchestrates parse → chunk → embed → store for a single document.

    Instantiated per-request or per-Celery task — it holds no mutable state
    between calls, so it is safe to share an instance across concurrent tasks
    if the underlying services support it (they do, as they are stateless).
    """

    def __init__(
        self,
        session: AsyncSession,
        storage_service: StorageService,
        parser_service: DocumentParserService,
        chunking_service: ChunkingService,
        embedding_service: EmbeddingService,
    ) -> None:
        self._session = session
        self._doc_repo = DocumentRepository(session)
        self._vector_repo = VectorRepository(session)
        self._storage = storage_service
        self._parser = parser_service
        self._chunker = chunking_service
        self._embedder = embedding_service

    async def process(
        self,
        *,
        document_id: str,
        user_id: str,
        force: bool = False,
    ) -> int:
        """
        Run the complete RAG indexing pipeline for a document.

        Args:
            document_id: UUID string of the Document record.
            user_id:     UUID string of the owning user (for ownership check).
            force:       If True, re-process even if status is already 'ready'.

        Returns:
            Number of chunks stored.

        Raises:
            DocumentNotFoundException: If the document doesn't exist or isn't owned by user.
            DocumentProcessingException: On any pipeline failure (logged + stored in DB).
        """
        # ── 1. Load document and guard ────────────────────────────────────────
        document = await self._doc_repo.get_by_id_and_user(document_id, user_id)
        if document is None:
            raise DocumentNotFoundException(document_id)

        if document.status == "ready" and not force:
            logger.info(
                "document_already_ready",
                document_id=document_id,
                chunk_count=document.chunk_count,
            )
            return document.chunk_count

        if document.status == "processing":
            logger.warning(
                "document_already_processing",
                document_id=document_id,
            )
            # Allow it through — Celery task retries may legitimately reach here

        # ── 2. Mark as processing ─────────────────────────────────────────────
        await self._doc_repo.update_status(document, "processing")
        await self._session.commit()

        logger.info(
            "document_processing_started",
            document_id=document_id,
            user_id=user_id,
            file_type=document.file_type,
            original_filename=document.original_filename,
        )

        try:
            # ── 3. Parse ──────────────────────────────────────────────────────
            parsed = await self._parser.parse(
                storage_path=document.storage_path,
                file_type=document.file_type,
                original_filename=document.original_filename,
            )

            # ── 4. Chunk ──────────────────────────────────────────────────────
            chunks = self._chunker.split(
                parsed=parsed,
                document_id=document_id,
            )

            # ── 5. Embed ──────────────────────────────────────────────────────
            chunks = await self._embedder.embed_chunks(
                chunks=chunks,
                document_id=document_id,
            )

            # ── 6. Delete old chunks (idempotent) then store new ones ─────────
            deleted = await self._vector_repo.delete_by_document_id(
                document_id=document_id,
                user_id=user_id,
            )
            if deleted:
                logger.info(
                    "old_chunks_deleted",
                    document_id=document_id,
                    deleted=deleted,
                )

            inserted = await self._vector_repo.store_chunks(
                chunks=chunks,
                document_id=document_id,
                user_id=user_id,
            )

            # ── 7. Mark ready ─────────────────────────────────────────────────
            await self._doc_repo.update_processing_results(
                document,
                chunk_count=inserted,
                page_count=parsed.page_count,
                word_count=parsed.word_count,
            )
            await self._doc_repo.update_status(document, "ready")
            await self._session.commit()

            logger.info(
                "document_processing_complete",
                document_id=document_id,
                chunks=inserted,
                pages=parsed.page_count,
                words=parsed.word_count,
            )
            return inserted

        except Exception as exc:
            # Roll back any partial inserts for this transaction
            await self._session.rollback()

            error_msg = str(exc)
            logger.error(
                "document_processing_failed",
                document_id=document_id,
                error=error_msg,
                exc_info=True,
            )

            # Persist failure status — use a fresh begin so the rollback above
            # doesn't take this UPDATE with it
            try:
                await self._doc_repo.update_status(
                    document,
                    "failed",
                    error_message=error_msg[:1000],
                )
                await self._session.commit()
            except Exception as db_exc:
                logger.error(
                    "failed_to_persist_failure_status",
                    document_id=document_id,
                    error=str(db_exc),
                )

            raise DocumentProcessingException(
                f"Processing failed for document {document_id}: {error_msg}"
            ) from exc
