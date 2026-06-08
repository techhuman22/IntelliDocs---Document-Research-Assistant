"""
Context builder service — assembles retrieved chunks into an LLM-ready context string.

Responsibilities:
  1. Merge the ranked list of RetrievedChunk objects into a single context string.
  2. Respect CONTEXT_MAX_TOKENS — stop adding chunks when the token budget is exhausted.
  3. Build a citations list suitable for display in the API response.
  4. Compute sufficiency metrics (are the results good enough to answer the query?).
  5. Return a BuiltContext object — the data contract with LangGraph agents (Phase 5).

Token estimation:
  Uses the same cl100k_base tiktoken tokenizer as ChunkingService.
  This is a conservative proxy for Gemini's token count.

Context format:
  Each chunk is prefixed with a citation header:
    [Source: annual_report.pdf, Page 3, Chunk 7]
    <chunk content>
  Chunks are separated by CONTEXT_SEPARATOR (default: "\n\n---\n\n").

Sufficiency scoring:
  is_sufficient = avg(top_3_similarity_scores) >= 0.75
  This heuristic flags queries where the retrieval found weak matches,
  so agents can decide whether to respond or ask for clarification.
"""

from app.config.settings import settings
from app.core.logging import get_logger
from app.schemas.rag import BuiltContext, RetrievedChunk
from app.services.chunking_service import count_tokens  # reuse the tokenizer

logger = get_logger(__name__)

# Minimum average similarity to declare the context "sufficient"
_SUFFICIENCY_THRESHOLD = 0.75
_TOP_N_FOR_SUFFICIENCY = 3


class ContextBuilderService:
    """
    Converts a list of RetrievedChunk objects into a BuiltContext.

    Instantiate once and call build() per request — no mutable state.
    """

    def __init__(
        self,
        max_tokens: int | None = None,
        separator: str | None = None,
    ) -> None:
        self._max_tokens = max_tokens or settings.CONTEXT_MAX_TOKENS
        self._separator = separator or settings.CONTEXT_SEPARATOR

    def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
    ) -> BuiltContext:
        """
        Assemble a BuiltContext from retrieved chunks.

        Args:
            query:  The original user query (included in BuiltContext for agent use).
            chunks: Ordered list from RetrievalService.search() — most similar first.

        Returns:
            BuiltContext ready for injection into an LLM prompt or for serialisation
            as the API response body.
        """
        if not chunks:
            return BuiltContext(
                query=query,
                context_text="",
                chunks=[],
                citations=[],
                total_tokens_estimate=0,
                is_sufficient=False,
                sufficiency_score=0.0,
            )

        context_parts: list[str] = []
        citations: list[dict] = []
        included_chunks: list[RetrievedChunk] = []
        token_budget = self._max_tokens

        for chunk in chunks:
            header = self._format_header(chunk)
            part = f"{header}\n{chunk.content}"
            part_tokens = count_tokens(part)

            if part_tokens > token_budget:
                # Try to fit a partial chunk if we have at least 100 tokens left
                if token_budget >= 100:
                    truncated = self._truncate_to_tokens(chunk.content, token_budget - count_tokens(header) - 5)
                    if truncated:
                        part = f"{header}\n{truncated}"
                        context_parts.append(part)
                        token_budget -= count_tokens(part)
                        included_chunks.append(chunk)
                        citations.append(self._build_citation(chunk, len(citations) + 1))
                break

            context_parts.append(part)
            token_budget -= part_tokens
            included_chunks.append(chunk)
            citations.append(self._build_citation(chunk, len(citations) + 1))

        context_text = self._separator.join(context_parts)
        total_tokens = count_tokens(context_text)

        sufficiency_score = self._compute_sufficiency(included_chunks)
        is_sufficient = sufficiency_score >= _SUFFICIENCY_THRESHOLD

        logger.info(
            "context_built",
            query_len=len(query),
            chunks_included=len(included_chunks),
            chunks_available=len(chunks),
            total_tokens=total_tokens,
            sufficiency_score=round(sufficiency_score, 3),
            is_sufficient=is_sufficient,
        )

        return BuiltContext(
            query=query,
            context_text=context_text,
            chunks=included_chunks,
            citations=citations,
            total_tokens_estimate=total_tokens,
            is_sufficient=is_sufficient,
            sufficiency_score=round(sufficiency_score, 4),
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _format_header(chunk: RetrievedChunk) -> str:
        """
        Build a human-readable citation header for each chunk.

        Example: "[Source: report.pdf, Page 3, Chunk 7]"
        The LLM uses these headers to attribute its answer to specific sources.
        """
        parts = [f"Source: {chunk.original_filename}"]
        if chunk.page_number is not None:
            parts.append(f"Page {chunk.page_number}")
        parts.append(f"Chunk {chunk.chunk_index}")
        return f"[{', '.join(parts)}]"

    @staticmethod
    def _build_citation(chunk: RetrievedChunk, position: int) -> dict:
        """Build a structured citation record for the API response."""
        return {
            "position": position,
            "document_id": str(chunk.document_id),
            "original_filename": chunk.original_filename,
            "chunk_index": chunk.chunk_index,
            "page_number": chunk.page_number,
            "similarity_score": chunk.similarity_score,
        }

    @staticmethod
    def _truncate_to_tokens(text: str, max_tokens: int) -> str:
        """
        Truncate text to fit within max_tokens using binary search.
        Returns an empty string if even a 20-word snippet exceeds max_tokens.
        """
        if max_tokens <= 0:
            return ""
        words = text.split()
        lo, hi = 0, len(words)
        result = ""
        while lo <= hi:
            mid = (lo + hi) // 2
            candidate = " ".join(words[:mid])
            if count_tokens(candidate) <= max_tokens:
                result = candidate
                lo = mid + 1
            else:
                hi = mid - 1
        return result

    @staticmethod
    def _compute_sufficiency(chunks: list[RetrievedChunk]) -> float:
        """
        Average similarity of the top N chunks.
        Returns 0.0 if no chunks were included.
        """
        if not chunks:
            return 0.0
        top_n = chunks[:_TOP_N_FOR_SUFFICIENCY]
        return sum(c.similarity_score for c in top_n) / len(top_n)
