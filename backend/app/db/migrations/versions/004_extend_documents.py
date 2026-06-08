"""Extend documents table — original_filename, stored_filename, mime_type

Revision ID: 004
Revises: 003
Create Date: 2024-01-03 00:00:00.000000 UTC

Adds columns required by the Phase 3 document management module:
  - original_filename : the user-supplied filename (display only)
  - stored_filename   : the UUID-based collision-proof name on disk
  - mime_type         : full MIME type for content-type accuracy
  - file_type index   : adds composite index for type-based filtering

Migration strategy:
  - original_filename and stored_filename are added as nullable first,
    then backfilled from file_name, then made NOT NULL.
    This pattern avoids a long table lock on backfill.
  - mime_type has a safe default so existing rows get a valid value.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: add new columns as nullable (avoids full table lock during add)
    op.add_column(
        "documents",
        sa.Column("original_filename", sa.String(500), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column("stored_filename", sa.String(500), nullable=True),
    )
    op.add_column(
        "documents",
        sa.Column(
            "mime_type",
            sa.String(100),
            nullable=False,
            server_default="application/octet-stream",
        ),
    )

    # Step 2: backfill new columns from the existing file_name column
    op.execute(
        """
        UPDATE documents
        SET
            original_filename = file_name,
            stored_filename   = file_name
        WHERE original_filename IS NULL
        """
    )

    # Step 3: backfill mime_type from file_type for pre-existing rows
    op.execute(
        """
        UPDATE documents
        SET mime_type = CASE file_type
            WHEN 'pdf'  THEN 'application/pdf'
            WHEN 'docx' THEN 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            WHEN 'txt'  THEN 'text/plain'
            ELSE 'application/octet-stream'
        END
        WHERE mime_type = 'application/octet-stream' AND file_type IS NOT NULL
        """
    )

    # Step 4: now that all rows have values, tighten to NOT NULL
    op.alter_column("documents", "original_filename", nullable=False)
    op.alter_column("documents", "stored_filename", nullable=False)

    # Step 5: add composite index for file_type filtering per user
    op.create_index(
        "ix_documents_user_id_file_type",
        "documents",
        ["user_id", "file_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_documents_user_id_file_type", table_name="documents")
    op.drop_column("documents", "mime_type")
    op.drop_column("documents", "stored_filename")
    op.drop_column("documents", "original_filename")
