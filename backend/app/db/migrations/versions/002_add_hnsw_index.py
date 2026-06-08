"""Add HNSW vector index on document_chunks.embedding

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 01:00:00.000000 UTC

The HNSW index is separated from the initial schema migration because:
  1. It cannot be created concurrently inside a transaction (PostgreSQL
     restriction). We disable autobegin and use op.execute() directly.
  2. On a table with existing data, HNSW creation is slow and should not
     block the rest of the schema migration.
  3. The index parameters (m, ef_construction) can be tuned independently
     once we have real data to measure recall vs. speed trade-offs.

HNSW parameters:
  m=16              — number of bi-directional links per node
                      Higher = better recall, more memory
  ef_construction=64 — size of dynamic candidate list during construction
                      Higher = better recall, slower build time

For 1M+ vectors, consider m=32, ef_construction=128.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # HNSW indexes cannot be created inside a transaction block.
    # We close the current transaction, create the index, then resume.
    op.execute("COMMIT")
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX CONCURRENTLY IF EXISTS ix_document_chunks_embedding_hnsw")
