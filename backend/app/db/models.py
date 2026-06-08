"""
SQLAlchemy ORM models for AgentFlow AI.

All models inherit from Base (app.db.base) and use:
  - UUID primary keys (gen_random_uuid() on the DB side)
  - created_at / updated_at managed by SQLAlchemy's onupdate
  - Explicit foreign keys with cascading deletes where appropriate
  - JSONB for semi-structured metadata and nested structures
  - pgvector's Vector type for embedding columns

Import order matters for Alembic: import this module in migrations/env.py
so that all table metadata is registered before autogenerate runs.
"""

import uuid
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# ─────────────────────────────────────────────────────────────────────────────
# Shared mixin — timestamps on every table
# ─────────────────────────────────────────────────────────────────────────────

class TimestampMixin:
    """Adds created_at and updated_at to any model that inherits it."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),        # SQLAlchemy sets this on UPDATE
        nullable=False,
    )


# ─────────────────────────────────────────────────────────────────────────────
# User
# ─────────────────────────────────────────────────────────────────────────────

class User(Base, TimestampMixin):
    """
    Registered users of the platform.

    plan_tier controls feature access:
      free       → limited uploads, no web search
      pro        → unlimited uploads, web search enabled
      enterprise → custom limits, admin dashboard access
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    plan_tier: Mapped[str] = mapped_column(
        String(50),
        default="free",
        nullable=False,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    documents: Mapped[list["Document"]] = relationship(
        "Document",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",              # never eager-load — always use explicit joins
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        "ChatSession",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        "RefreshToken",
        back_populates="user",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


# ─────────────────────────────────────────────────────────────────────────────
# Document
# ─────────────────────────────────────────────────────────────────────────────

class Document(Base, TimestampMixin):
    """
    Uploaded files. A document goes through a processing pipeline:
      pending → processing → ready | failed

    Two filename fields serve different purposes:
      original_filename — the name the user gave the file (display only)
      stored_filename   — the name on disk (UUID-based, collision-proof, URL-safe)

    storage_path is the full absolute path to the file on the local filesystem
    (or the S3 key in production). It is built by StorageService and is the
    authoritative pointer to the physical file.

    chunk_count is denormalized here for fast display — updated by the
    background processing worker after chunking completes (Phase 4).
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Filename fields ───────────────────────────────────────────────────────
    # original_filename: exactly what the user uploaded — used for display only
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)

    # stored_filename: the safe, unique name written to disk
    # Format: {uuid4}-{sanitized_original}.{ext}  e.g. "a1b2c3d4-report.pdf"
    stored_filename: Mapped[str] = mapped_column(String(500), nullable=False)

    # Backward-compat alias used by existing Phase-1 code and migrations:
    # file_name maps to the original_filename concept.
    # New code should use original_filename / stored_filename directly.
    file_name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment="Deprecated alias for original_filename — kept for migration compatibility",
    )

    file_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )  # 'pdf' | 'docx' | 'txt'

    # Full MIME type for accurate content-type headers on download
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="application/octet-stream",
    )

    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Absolute path on disk (local) or object key (S3 in production)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)

    # Processing pipeline status
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )  # 'pending' | 'processing' | 'ready' | 'failed'

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Populated by the document processing worker (Phase 4)
    page_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    word_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Flexible metadata: title, author, language, extraction timestamps, etc.
    doc_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        name="metadata",
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="documents", lazy="noload")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        "DocumentChunk",
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_documents_user_id_status", "user_id", "status"),
        Index("ix_documents_user_id_file_type", "user_id", "file_type"),
        Index("ix_documents_created_at", "created_at"),
    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    @property
    def is_ready(self) -> bool:
        return self.status == "ready"

    @property
    def is_processing(self) -> bool:
        return self.status in ("pending", "processing")

    @property
    def file_size_mb(self) -> float:
        return round(self.file_size_bytes / (1024 * 1024), 2)

    def __repr__(self) -> str:
        return (
            f"<Document id={self.id} "
            f"original_filename={self.original_filename} "
            f"status={self.status}>"
        )


# ─────────────────────────────────────────────────────────────────────────────
# DocumentChunk
# ─────────────────────────────────────────────────────────────────────────────

class DocumentChunk(Base):
    """
    Individual text chunks with their pgvector embeddings.

    The HNSW index on the embedding column enables sub-millisecond
    approximate nearest-neighbor search over millions of vectors.

    created_at only — chunks are immutable once created.
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # SHA-256 of content — used to skip re-embedding identical chunks
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # 768-dimensional vector from Gemini text-embedding-004
    embedding: Mapped[list[float]] = mapped_column(
        Vector(768),
        nullable=False,
    )

    # Section heading, surrounding context, etc.
    chunk_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        name="metadata",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    document: Mapped["Document"] = relationship(
        "Document", back_populates="chunks", lazy="noload"
    )

    # ── Indexes and Constraints ───────────────────────────────────────────────
    __table_args__ = (
        # Enforce ordering integrity: each chunk_index is unique per document
        UniqueConstraint("document_id", "chunk_index", name="uq_chunk_document_index"),
        Index("ix_document_chunks_user_id", "user_id"),
        # NOTE: The HNSW vector index is created in a separate Alembic migration
        # using op.execute() because SQLAlchemy does not natively generate it.
        # See: migrations/versions/002_add_hnsw_index.py
    )

    def __repr__(self) -> str:
        return f"<DocumentChunk id={self.id} doc={self.document_id} idx={self.chunk_index}>"


# ─────────────────────────────────────────────────────────────────────────────
# ChatSession
# ─────────────────────────────────────────────────────────────────────────────

class ChatSession(Base, TimestampMixin):
    """
    A conversation session. A session is always scoped to one or more documents.

    memory_summary holds an LLM-generated compression of past conversation —
    used to seed context when a session is resumed after the Redis cache expires.

    document_ids is a PostgreSQL UUID array, enabling GIN index-based filtering:
      WHERE document_ids && ARRAY['doc-uuid-1']::uuid[]
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )  # auto-generated from first user message
    document_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        default=list,
    )
    session_type: Mapped[str] = mapped_column(
        String(50),
        default="chat",
        nullable=False,
    )  # 'chat' | 'quiz' | 'flashcard' | 'comparison'

    # LLM-compressed conversation summary for long-term memory
    memory_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    message_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship(
        "User", back_populates="chat_sessions", lazy="noload"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="noload",
        order_by="Message.created_at",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_chat_sessions_user_id_archived", "user_id", "is_archived"),
        Index("ix_chat_sessions_last_active", "last_active_at"),
        # GIN index on document_ids array for fast "sessions using document X" lookups
        Index(
            "ix_chat_sessions_document_ids_gin",
            "document_ids",
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} user={self.user_id} type={self.session_type}>"


# ─────────────────────────────────────────────────────────────────────────────
# Message
# ─────────────────────────────────────────────────────────────────────────────

class Message(Base):
    """
    Individual turns in a chat session.

    structured_data holds JSON payloads for non-text response types
    (quiz questions, flashcards, comparison tables).

    sources and agent_path are stored as JSONB for flexible schema
    evolution without migration overhead.
    """

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )  # 'user' | 'assistant' | 'system'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(50),
        default="text",
        nullable=False,
    )  # 'text' | 'quiz' | 'flashcard' | 'comparison'

    # JSON payload for structured outputs (quiz, flashcard, comparison)
    structured_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Router agent's intent classification
    intent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    # Citations: [{"doc_name": str, "chunk_index": int, "page": int, "score": float}]
    sources: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Ordered list of agent names that contributed to this response
    agent_path: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Performance tracking
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    session: Mapped["ChatSession"] = relationship(
        "ChatSession", back_populates="messages", lazy="noload"
    )
    agent_logs: Mapped[list["AgentLog"]] = relationship(
        "AgentLog",
        back_populates="message",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_messages_session_created", "session_id", "created_at"),
        Index("ix_messages_role", "role"),
    )

    def __repr__(self) -> str:
        return f"<Message id={self.id} role={self.role} session={self.session_id}>"


# ─────────────────────────────────────────────────────────────────────────────
# AgentLog
# ─────────────────────────────────────────────────────────────────────────────

class AgentLog(Base):
    """
    Per-agent observability record. One row per agent invocation per message.

    Enables:
      - Debugging agent failures post-hoc
      - Cost tracking per agent (token_input + token_output × price)
      - Latency analysis per agent type
      - Audit trail for AI decisions

    input_snapshot and output_snapshot store the relevant state fields
    before and after the agent ran — not the full graph state, which
    could be very large. Only the fields the agent consumed/produced.
    """

    __tablename__ = "agent_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    message_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("messages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
    )  # 'router' | 'retrieval' | 'research' | 'summary' | etc.

    # State snapshots — store only the relevant subset of AgentFlowState
    input_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Tool calls made by this agent: [{"tool": str, "input": dict, "output": str}]
    tool_calls: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Performance
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_input: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    token_output: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(
        String(50),
        default="success",
        nullable=False,
        index=True,
    )  # 'success' | 'error' | 'skipped'
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    message: Mapped[Optional["Message"]] = relationship(
        "Message", back_populates="agent_logs", lazy="noload"
    )

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_agent_logs_session_agent", "session_id", "agent_name"),
        Index("ix_agent_logs_status_created", "status", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<AgentLog id={self.id} agent={self.agent_name} status={self.status}>"


# ─────────────────────────────────────────────────────────────────────────────
# RefreshToken
# ─────────────────────────────────────────────────────────────────────────────

class RefreshToken(Base):
    """
    Persistent record of every issued refresh token.

    Storing refresh tokens in the database (in addition to Redis) gives us:
      - A complete audit trail of all login sessions
      - The ability to revoke all sessions for a user at once
      - Reliable expiry enforcement independent of Redis eviction policy
      - Token rotation: each use invalidates the old token and issues a new one

    Security note: we store a SHA-256 hash of the raw token JTI, not the
    JTI itself. This means a database breach cannot be used to forge tokens.

    Lookup flow:
      1. Decode JWT → extract JTI
      2. Hash the JTI → look up in this table
      3. Verify not revoked and not expired
      4. Compare user_id against JWT sub claim
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hash of the JWT's jti claim — never store the raw jti
    jti_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        index=True,
    )

    # Device/session context — useful for "active sessions" UI
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)  # IPv6 max = 45

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user: Mapped["User"] = relationship("User", back_populates="refresh_tokens", lazy="noload")

    # ── Indexes ───────────────────────────────────────────────────────────────
    __table_args__ = (
        Index("ix_refresh_tokens_user_id_revoked", "user_id", "is_revoked"),
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    @property
    def is_expired(self) -> bool:
        from datetime import timezone as tz
        return datetime.now(tz=tz.utc) >= self.expires_at

    @property
    def is_valid(self) -> bool:
        return not self.is_revoked and not self.is_expired

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user={self.user_id} revoked={self.is_revoked}>"
