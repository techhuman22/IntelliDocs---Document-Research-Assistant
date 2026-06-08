"""Add char_count and full-text search index to document_chunks

Revision ID: 005
Revises: 004
Create Date: 2024-01-04 00:00:00.000000 UTC

Adds:
  - char_count column: character count of the chunk text for fast display
  - GIN tsvector index on content: enables full-text search as a hybrid
    retrieval mode alongside vector similarity (used in Phase 5)

Both changes are purely additive — no existing data is modified.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # char_count: stored so retrievers can estimate context window usage
    # without loading the full content column
    op.add_column(
        "document_chunks",
        sa.Column(
            "char_count",
            sa.Integer(),
            nullable=True,
            comment="Character count of the chunk content.",
        ),
    )

    # Backfill char_count from existing content
    op.execute(
        "UPDATE document_chunks SET char_count = LENGTH(content) WHERE char_count IS NULL"
    )

    # GIN index on to_tsvector for English full-text search
    # CONCURRENTLY avoids locking the table during index build
    op.execute("COMMIT")
    op.execute(
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS
            ix_document_chunks_content_fts
        ON document_chunks
        USING gin(to_tsvector('english', content))
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX CONCURRENTLY IF EXISTS ix_document_chunks_content_fts"
    )
    op.drop_column("document_chunks", "char_count")
