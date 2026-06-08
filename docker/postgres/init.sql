-- PostgreSQL initialization script.
-- Runs once when the postgres container is first created.
-- The pgvector/pgvector:pg16 image pre-installs the pgvector extension binary,
-- but we still need to CREATE EXTENSION in the target database.

-- Install pgvector extension (idempotent)
CREATE EXTENSION IF NOT EXISTS vector;

-- Install uuid-ossp for gen_random_uuid() (included in pg16+)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Install pg_trgm for future full-text search on document content
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Set default timezone to UTC for all connections
ALTER DATABASE agentflow SET timezone TO 'UTC';
