"""Initial schema — all tables and indexes

Revision ID: 001
Revises: None
Create Date: 2024-01-01 00:00:00.000000 UTC

Creates:
  - pgvector extension
  - users
  - documents
  - document_chunks  (with Vector(768) column)
  - chat_sessions
  - messages
  - agent_logs

The HNSW index on document_chunks.embedding is in migration 002
because it can be created concurrently (CONCURRENTLY keyword) after
data is loaded, which reduces initial migration time.
"""

from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Revision identifiers
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Extensions ────────────────────────────────────────────────────────────
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ── users ─────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("plan_tier", sa.String(50), nullable=False, server_default="free"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_plan_tier", "users", ["plan_tier"])

    # ── documents ─────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("file_name", sa.String(500), nullable=False),
        sa.Column("file_type", sa.String(50), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_created_at", "documents", ["created_at"])
    op.create_index("ix_documents_user_id_status", "documents", ["user_id", "status"])

    # ── document_chunks ───────────────────────────────────────────────────────
    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=True),
        # pgvector 768-dimensional column (Gemini text-embedding-004)
        sa.Column("embedding", pgvector.sqlalchemy.Vector(768), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_user_id", "document_chunks", ["user_id"])
    op.create_index("ix_document_chunks_content_hash", "document_chunks", ["content_hash"])

    # ── chat_sessions ─────────────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column(
            "document_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("session_type", sa.String(50), nullable=False, server_default="chat"),
        sa.Column("memory_summary", sa.Text(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_active_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])
    op.create_index("ix_chat_sessions_last_active", "chat_sessions", ["last_active_at"])
    op.create_index("ix_chat_sessions_user_id_archived", "chat_sessions", ["user_id", "is_archived"])
    # GIN index for UUID array search
    op.create_index(
        "ix_chat_sessions_document_ids_gin",
        "chat_sessions",
        ["document_ids"],
        postgresql_using="gin",
    )

    # ── messages ──────────────────────────────────────────────────────────────
    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("structured_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("intent", sa.String(50), nullable=True),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("agent_path", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_messages_session_id", "messages", ["session_id"])
    op.create_index("ix_messages_user_id", "messages", ["user_id"])
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])
    op.create_index("ix_messages_role", "messages", ["role"])

    # ── agent_logs ────────────────────────────────────────────────────────────
    op.create_table(
        "agent_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("input_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("output_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tool_calls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_logs_message_id", "agent_logs", ["message_id"])
    op.create_index("ix_agent_logs_session_id", "agent_logs", ["session_id"])
    op.create_index("ix_agent_logs_user_id", "agent_logs", ["user_id"])
    op.create_index("ix_agent_logs_agent_name", "agent_logs", ["agent_name"])
    op.create_index("ix_agent_logs_session_agent", "agent_logs", ["session_id", "agent_name"])
    op.create_index("ix_agent_logs_status_created", "agent_logs", ["status", "created_at"])
    op.create_index("ix_agent_logs_created_at", "agent_logs", ["created_at"])


def downgrade() -> None:
    # Drop in reverse dependency order
    op.drop_table("agent_logs")
    op.drop_table("messages")
    op.drop_table("chat_sessions")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("users")
