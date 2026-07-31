"""Switch embedding dimension from 768 to 384

Revision ID: 006
Revises: 005
Create Date: 2024-07-31 00:00:00.000000 UTC

Switches the embedding model from all-mpnet-base-v2 (768-dim, ~420 MB)
to all-MiniLM-L6-v2 (384-dim, ~80 MB) to fit within Render free-tier
memory limits (512 MB).

Since this is a fresh deployment with no existing data, this migration
simply drops the old HNSW index, alters the column type, and recreates
the index on the new dimension.

If you have existing embeddings, you MUST re-embed all documents after
running this migration.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the existing HNSW index (it was built for 768-dim vectors)
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")

    # 2. Alter the embedding column from Vector(768) to Vector(384)
    #    Using raw SQL because Alembic's op.alter_column doesn't handle
    #    pgvector type changes cleanly.
    op.execute(
        """
        ALTER TABLE document_chunks
        ALTER COLUMN embedding TYPE vector(384)
        USING embedding::vector(384)
        """
    )

    # 3. Recreate the HNSW index for 384-dim vectors
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
    # Reverse: drop index, widen back to 768, recreate index
    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute(
        """
        ALTER TABLE document_chunks
        ALTER COLUMN embedding TYPE vector(768)
        USING embedding::vector(768)
        """
    )
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
