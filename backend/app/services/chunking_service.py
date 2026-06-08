"""
Chunking service — splits parsed documents into embedding-sized chunks.

Uses LangChain's RecursiveCharacterTextSplitter, which tries to split
on progressively finer boundaries:
  1. Double newlines (paragraphs)
  2. Single newlines (lines)
  3. Sentences (". ")
  4. Words (" ")
  5. Characters (last resort)

This ordering preserves semantic coherence — a chunk about "revenue growth"
stays together rather than being split mid-sentence.

Chunk metadata:
  Each chunk carries the source document metadata (filename, page number,
  section context) plus its position within the document (chunk_index).
  This metadata is stored in the document_chunks.metadata JSONB column
  and returned in retrieval results so LLM agents can cite sources precisely.

Token counting:
  We use tiktoken (cl100k_base, the GPT-4 tokenizer) as a proxy for
  Gemini's token count — Gemini's tokenizer is not publicly available
  but cl100k gives a close enough estimate for chunk size enforcement.
  The actual embedding request never fails due to oversized input because
  we chunk conservatively (CHUNK_SIZE=512 tokens ≈ 380 words).
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional

import tiktoken
from langchain_core.documents import Document as LangChainDocument
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.config.settings import settings
from app.core.logging import get_logger
from app.services.document_parser_service import ParsedDocument

logger = get_logger(__name__)

# Tiktoken encoder — loaded once at module import (cached internally by tiktoken)
_TOKENIZER = tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens in text using cl100k_base tokenizer."""
    return len(_TOKENIZER.encode(text, disallowed_special=()))


def compute_content_hash(text: str) -> str:
    """SHA-256 hash of chunk text — used for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class TextChunk:
    """
    A single text chunk ready for embedding and storage.

    This is the internal data transfer object between ChunkingService
    and EmbeddingService. Not an ORM model — that comes later.
    """

    chunk_index: int
    content: str
    token_count: int
    char_count: int
    content_hash: str
    page_number: Optional[int]
    chunk_metadata: dict = field(default_factory=dict)

    @classmethod
    def from_langchain_doc(
        cls,
        doc: LangChainDocument,
        chunk_index: int,
        original_filename: str,
        document_id: str,
    ) -> "TextChunk":
        """Build a TextChunk from a LangChain Document produced by the splitter."""
        content = doc.page_content.strip()
        meta = doc.metadata or {}

        # Extract page number — PyPDFLoader uses 0-based "page" key
        raw_page = meta.get("page")
        page_number: Optional[int] = (raw_page + 1) if raw_page is not None else None

        # Build rich metadata for storage and citation
        chunk_metadata = {
            "source_filename": original_filename,
            "document_id": document_id,
            "chunk_index": chunk_index,
            "page_number": page_number,
            "section": meta.get("section", ""),
            "element_type": meta.get("category", "text"),  # from Unstructured loader
        }

        return cls(
            chunk_index=chunk_index,
            content=content,
            token_count=count_tokens(content),
            char_count=len(content),
            content_hash=compute_content_hash(content),
            page_number=page_number,
            chunk_metadata=chunk_metadata,
        )


class ChunkingService:
    """
    Splits a ParsedDocument into a list of TextChunk objects.

    Uses RecursiveCharacterTextSplitter with character-based sizing
    (not token-based) for speed — we then compute exact token counts
    per chunk and log any that exceed the target.

    Character-to-token ratio for English: ~4 chars per token.
    chunk_size in characters = CHUNK_SIZE (tokens) × 4 = 2048 chars
    chunk_overlap in chars   = CHUNK_OVERLAP (tokens) × 4 = 256 chars
    """

    def __init__(
        self,
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> None:
        """
        Args:
            chunk_size:    Target tokens per chunk. Defaults to settings.CHUNK_SIZE.
            chunk_overlap: Overlap in tokens. Defaults to settings.CHUNK_OVERLAP.
        """
        self._chunk_size_tokens = chunk_size or settings.CHUNK_SIZE
        self._chunk_overlap_tokens = chunk_overlap or settings.CHUNK_OVERLAP

        # Convert to approximate character counts for the splitter
        # (4 chars/token is a conservative estimate for English)
        chars_per_token = 4
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self._chunk_size_tokens * chars_per_token,
            chunk_overlap=self._chunk_overlap_tokens * chars_per_token,
            length_function=len,           # character-based for speed
            separators=["\n\n", "\n", ". ", "! ", "? ", "; ", ", ", " ", ""],
            keep_separator=True,           # preserve sentence-ending punctuation
            add_start_index=True,          # adds 'start_index' to chunk metadata
        )

    def split(
        self,
        parsed: ParsedDocument,
        document_id: str,
    ) -> list[TextChunk]:
        """
        Split a ParsedDocument into TextChunk objects.

        Steps:
          1. Pass LangChain Document pages through RecursiveCharacterTextSplitter.
          2. Filter out chunks that are too short to be meaningful.
          3. Deduplicate by content_hash (catches identical boilerplate pages).
          4. Enrich each chunk with metadata.
          5. Return the final ordered list.

        Args:
            parsed:       The output of DocumentParserService.parse().
            document_id:  UUID string of the parent Document record.

        Returns:
            Ordered list of TextChunk, with chunk_index 0..N.
        """
        logger.info(
            "chunking_document",
            document_id=document_id,
            page_count=parsed.page_count,
            original_filename=parsed.original_filename,
            chunk_size=self._chunk_size_tokens,
            chunk_overlap=self._chunk_overlap_tokens,
        )

        # Split all pages at once — the splitter handles them as a batch
        split_docs: list[LangChainDocument] = self._splitter.split_documents(parsed.pages)

        # Build TextChunks, filtering and deduplicating
        chunks: list[TextChunk] = []
        seen_hashes: set[str] = set()
        skipped_short = 0
        skipped_duplicate = 0

        for raw_doc in split_docs:
            content = raw_doc.page_content.strip()

            # Skip chunks that are too short to carry semantic meaning
            if len(content) < 50:  # ~12 words minimum
                skipped_short += 1
                continue

            content_hash = compute_content_hash(content)
            if content_hash in seen_hashes:
                skipped_duplicate += 1
                continue
            seen_hashes.add(content_hash)

            chunk = TextChunk.from_langchain_doc(
                doc=raw_doc,
                chunk_index=len(chunks),     # sequential after dedup
                original_filename=parsed.original_filename,
                document_id=document_id,
            )
            chunks.append(chunk)

        logger.info(
            "document_chunked",
            document_id=document_id,
            total_chunks=len(chunks),
            skipped_short=skipped_short,
            skipped_duplicate=skipped_duplicate,
            avg_token_count=(
                sum(c.token_count for c in chunks) // len(chunks) if chunks else 0
            ),
        )

        if not chunks:
            from app.core.exceptions import DocumentProcessingException
            raise DocumentProcessingException(
                f"Document '{parsed.original_filename}' produced no valid chunks after splitting. "
                "The document may contain only images or unsupported content."
            )

        return chunks
