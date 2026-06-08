"""
Unit tests for ChunkingService.

All tests are offline (no Gemini, no DB, no filesystem).
ParsedDocument is constructed manually from LangChain Documents.
"""

import pytest
from langchain_core.documents import Document as LangChainDocument

from app.services.chunking_service import (
    ChunkingService,
    TextChunk,
    compute_content_hash,
    count_tokens,
)
from app.services.document_parser_service import ParsedDocument


def _make_parsed(texts: list[str], filename: str = "test.pdf") -> ParsedDocument:
    pages = [
        LangChainDocument(page_content=t, metadata={"page": i, "source": filename})
        for i, t in enumerate(texts)
    ]
    return ParsedDocument(
        pages=pages,
        file_type="pdf",
        original_filename=filename,
        storage_path=f"/uploads/{filename}",
    )


LOREM = (
    "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
    "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris. "
)


class TestCountTokens:
    def test_empty_string(self):
        assert count_tokens("") == 0

    def test_single_word(self):
        assert count_tokens("hello") > 0

    def test_long_text_proportional(self):
        short = count_tokens("hello world")
        long_ = count_tokens("hello world " * 100)
        assert long_ > short


class TestComputeContentHash:
    def test_deterministic(self):
        assert compute_content_hash("abc") == compute_content_hash("abc")

    def test_different_inputs(self):
        assert compute_content_hash("abc") != compute_content_hash("xyz")

    def test_length_64(self):
        assert len(compute_content_hash("any text")) == 64


class TestTextChunkFromLangchainDoc:
    def test_page_number_conversion(self):
        doc = LangChainDocument(
            page_content="Some content here for testing purposes.",
            metadata={"page": 0},   # 0-based from PyPDFLoader
        )
        chunk = TextChunk.from_langchain_doc(
            doc=doc, chunk_index=0, original_filename="f.pdf", document_id="uuid-abc"
        )
        assert chunk.page_number == 1   # converted to 1-based

    def test_no_page_metadata(self):
        doc = LangChainDocument(page_content="No page here for testing purposes.", metadata={})
        chunk = TextChunk.from_langchain_doc(
            doc=doc, chunk_index=0, original_filename="f.txt", document_id="uuid-abc"
        )
        assert chunk.page_number is None

    def test_metadata_populated(self):
        doc = LangChainDocument(
            page_content="Check metadata fields are set correctly.",
            metadata={"page": 2},
        )
        chunk = TextChunk.from_langchain_doc(
            doc=doc, chunk_index=5, original_filename="report.pdf", document_id="doc-1"
        )
        assert chunk.chunk_metadata["source_filename"] == "report.pdf"
        assert chunk.chunk_metadata["document_id"] == "doc-1"
        assert chunk.chunk_metadata["chunk_index"] == 5

    def test_char_count_correct(self):
        content = "Exactly this content."
        doc = LangChainDocument(page_content=content, metadata={})
        chunk = TextChunk.from_langchain_doc(
            doc=doc, chunk_index=0, original_filename="f.txt", document_id="d"
        )
        assert chunk.char_count == len(content)


class TestChunkingService:
    def test_basic_split_returns_chunks(self):
        text = LOREM * 20   # ~2000 chars
        parsed = _make_parsed([text])
        svc = ChunkingService(chunk_size=128, chunk_overlap=16)
        chunks = svc.split(parsed, document_id="doc-001")
        assert len(chunks) >= 1
        assert all(isinstance(c, TextChunk) for c in chunks)

    def test_chunk_indices_sequential(self):
        text = LOREM * 30
        parsed = _make_parsed([text])
        svc = ChunkingService(chunk_size=64, chunk_overlap=8)
        chunks = svc.split(parsed, document_id="doc-001")
        for i, c in enumerate(chunks):
            assert c.chunk_index == i

    def test_deduplication(self):
        # Identical pages should produce fewer chunks than naive count
        identical_text = LOREM * 10
        parsed = _make_parsed([identical_text, identical_text, identical_text])
        svc = ChunkingService(chunk_size=256, chunk_overlap=32)
        chunks = svc.split(parsed, document_id="doc-dup")
        hashes = [c.content_hash for c in chunks]
        assert len(hashes) == len(set(hashes)), "Duplicate chunks were not filtered"

    def test_short_content_filtered(self):
        # Very short page + normal page
        parsed = _make_parsed(["Hi.", LOREM * 10])
        svc = ChunkingService(chunk_size=256, chunk_overlap=32)
        chunks = svc.split(parsed, document_id="doc-short")
        # No chunk should have fewer than 50 chars
        assert all(len(c.content) >= 50 for c in chunks)

    def test_raises_on_empty_document(self):
        # All content is too short — should raise DocumentProcessingException
        parsed = _make_parsed(["Hi.", "Ok.", "x."])
        svc = ChunkingService()
        from app.core.exceptions import DocumentProcessingException
        with pytest.raises(DocumentProcessingException):
            svc.split(parsed, document_id="doc-empty")

    def test_content_hash_is_sha256(self):
        text = LOREM * 20
        parsed = _make_parsed([text])
        svc = ChunkingService(chunk_size=512, chunk_overlap=64)
        chunks = svc.split(parsed, document_id="doc-hash")
        for c in chunks:
            assert len(c.content_hash) == 64
            assert all(ch in "0123456789abcdef" for ch in c.content_hash)

    def test_token_count_gt_zero(self):
        text = LOREM * 20
        parsed = _make_parsed([text])
        svc = ChunkingService(chunk_size=256, chunk_overlap=32)
        chunks = svc.split(parsed, document_id="doc-tok")
        assert all(c.token_count > 0 for c in chunks)

    def test_multi_page_document(self):
        pages = [LOREM * 5 for _ in range(5)]
        parsed = _make_parsed(pages)
        svc = ChunkingService(chunk_size=128, chunk_overlap=16)
        chunks = svc.split(parsed, document_id="doc-multi")
        assert len(chunks) >= 5  # at least one chunk per page
