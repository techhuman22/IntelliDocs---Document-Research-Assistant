"""
Document parser service — text extraction from PDF, DOCX, and TXT files.

Uses LangChain document loaders as the extraction backend because they:
  - Handle edge cases in PDF encoding (multi-column, scanned text fallback)
  - Preserve page metadata from PDFs
  - Return LangChain Document objects, which plug directly into the splitter

Parsed result is a list of LangChain Document objects, each carrying:
  - page_content: the extracted text for that page/section
  - metadata:     source info (file path, page number, etc.)

The service is stateless — instantiate once per processing job.
"""

import io
from pathlib import Path
from typing import Optional

from langchain_community.document_loaders import (
    PyPDFLoader,
    Docx2txtLoader,
    TextLoader,
    UnstructuredFileLoader,
)
from langchain_core.documents import Document as LangChainDocument

from app.core.exceptions import DocumentProcessingException, ValidationException
from app.core.logging import get_logger

logger = get_logger(__name__)

# File type → loader class mapping
_LOADER_MAP: dict[str, type] = {
    "pdf":  PyPDFLoader,
    "docx": Docx2txtLoader,
    "txt":  TextLoader,
}


class ParsedDocument:
    """
    Container for the output of the parser service.
    Holds LangChain Document objects plus summary statistics.
    """

    def __init__(
        self,
        pages: list[LangChainDocument],
        file_type: str,
        original_filename: str,
        storage_path: str,
    ) -> None:
        self.pages = pages
        self.file_type = file_type
        self.original_filename = original_filename
        self.storage_path = storage_path

    @property
    def full_text(self) -> str:
        """All page content concatenated with newlines."""
        return "\n\n".join(p.page_content for p in self.pages if p.page_content.strip())

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def word_count(self) -> int:
        return len(self.full_text.split())

    @property
    def char_count(self) -> int:
        return len(self.full_text)

    def is_empty(self) -> bool:
        return not self.full_text.strip()


class DocumentParserService:
    """
    Extracts clean text from uploaded files.

    Design:
      - Each file type gets its dedicated LangChain loader.
      - PyPDFLoader extracts page-by-page, preserving page numbers in metadata.
      - Docx2txtLoader handles paragraph structure in DOCX files.
      - TextLoader handles plain text with encoding detection.
      - Falls back to UnstructuredFileLoader for robustness on malformed files.

    The service operates on storage_path (absolute path on disk).
    It does NOT do chunking — that is ChunkingService's responsibility.
    """

    async def parse(
        self,
        *,
        storage_path: str,
        file_type: str,
        original_filename: str,
    ) -> ParsedDocument:
        """
        Extract text from a document file.

        Args:
            storage_path:      Absolute path to the file on disk.
            file_type:         One of 'pdf', 'docx', 'txt'.
            original_filename: Original user-facing filename (used in logs/metadata).

        Returns:
            ParsedDocument containing a list of LangChain Document objects.

        Raises:
            DocumentProcessingException on any parsing failure.
        """
        path = Path(storage_path)
        if not path.exists():
            raise DocumentProcessingException(
                f"File not found at storage path: {storage_path}"
            )

        logger.info(
            "parsing_document",
            file_type=file_type,
            original_filename=original_filename,
            size_bytes=path.stat().st_size,
        )

        try:
            pages = await self._extract(storage_path=storage_path, file_type=file_type)
        except DocumentProcessingException:
            raise
        except Exception as exc:
            logger.error(
                "document_parsing_failed",
                file_type=file_type,
                original_filename=original_filename,
                error=str(exc),
            )
            raise DocumentProcessingException(
                f"Failed to parse {file_type.upper()} file '{original_filename}': {exc}"
            ) from exc

        parsed = ParsedDocument(
            pages=pages,
            file_type=file_type,
            original_filename=original_filename,
            storage_path=storage_path,
        )

        if parsed.is_empty():
            raise DocumentProcessingException(
                f"No extractable text found in '{original_filename}'. "
                "The file may be scanned, image-based, or password-protected."
            )

        logger.info(
            "document_parsed",
            original_filename=original_filename,
            page_count=parsed.page_count,
            word_count=parsed.word_count,
            char_count=parsed.char_count,
        )

        return parsed

    # ── Private: per-type extraction ──────────────────────────────────────────

    async def _extract(
        self,
        *,
        storage_path: str,
        file_type: str,
    ) -> list[LangChainDocument]:
        """Dispatch to the correct loader and return LangChain Document pages."""

        if file_type == "pdf":
            return await self._extract_pdf(storage_path)
        elif file_type == "docx":
            return await self._extract_docx(storage_path)
        elif file_type == "txt":
            return await self._extract_txt(storage_path)
        else:
            raise DocumentProcessingException(f"Unsupported file type: {file_type}")

    @staticmethod
    async def _extract_pdf(storage_path: str) -> list[LangChainDocument]:
        """
        Extract PDF text page-by-page using PyPDFLoader.

        Each returned Document represents one PDF page and carries:
          metadata["page"]:   0-based page index
          metadata["source"]: absolute file path

        Falls back to UnstructuredFileLoader if PyPDF fails (e.g. malformed PDF).
        """
        try:
            loader = PyPDFLoader(storage_path)
            # LangChain loaders are synchronous — run in the event loop's default executor
            import asyncio
            pages = await asyncio.get_event_loop().run_in_executor(None, loader.load)

            # Filter out empty pages (scanned PDFs with no text layer)
            non_empty = [p for p in pages if p.page_content.strip()]
            if non_empty:
                return non_empty

            # Fallback: try Unstructured for better scanned-PDF handling
            logger.warning("pdf_fallback_to_unstructured", path=storage_path)
            return await DocumentParserService._extract_unstructured(storage_path)

        except Exception as exc:
            logger.warning(
                "pypdf_failed_trying_unstructured",
                path=storage_path,
                error=str(exc),
            )
            return await DocumentParserService._extract_unstructured(storage_path)

    @staticmethod
    async def _extract_docx(storage_path: str) -> list[LangChainDocument]:
        """
        Extract DOCX text using Docx2txtLoader.

        Returns a single Document with all text (no per-page split —
        DOCX doesn't have a fixed page concept). The chunking stage
        will split it into appropriate pieces.
        """
        import asyncio
        loader = Docx2txtLoader(storage_path)
        docs = await asyncio.get_event_loop().run_in_executor(None, loader.load)

        # Enrich metadata
        for doc in docs:
            doc.metadata["source"] = storage_path
            doc.metadata["file_type"] = "docx"

        return docs

    @staticmethod
    async def _extract_txt(storage_path: str) -> list[LangChainDocument]:
        """
        Extract plain text using TextLoader with automatic encoding detection.

        Tries UTF-8 first, falls back to latin-1 which accepts any byte sequence.
        """
        import asyncio

        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                loader = TextLoader(storage_path, encoding=encoding)
                docs = await asyncio.get_event_loop().run_in_executor(None, loader.load)
                for doc in docs:
                    doc.metadata["source"] = storage_path
                    doc.metadata["file_type"] = "txt"
                    doc.metadata["encoding"] = encoding
                return docs
            except UnicodeDecodeError:
                continue

        raise DocumentProcessingException(
            f"Could not decode text file. Tried UTF-8 and latin-1 encodings."
        )

    @staticmethod
    async def _extract_unstructured(storage_path: str) -> list[LangChainDocument]:
        """
        Fallback extractor using UnstructuredFileLoader.
        Handles a wider range of formats and encodings than dedicated loaders.
        """
        import asyncio

        loader = UnstructuredFileLoader(
            storage_path,
            mode="elements",
            strategy="fast",
        )
        docs = await asyncio.get_event_loop().run_in_executor(None, loader.load)
        return docs if docs else []
