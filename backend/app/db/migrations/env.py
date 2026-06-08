"""
Alembic environment configuration.

This file runs in two modes:
  1. --autogenerate: compares ORM models against the live DB and generates
     a migration file with the differences.
  2. Normal migration run: applies pending migration scripts to the DB.

Key integration points:
  - Imports Base from app.db.base — Alembic uses Base.metadata to know
    which tables exist in the ORM layer.
  - Imports all model modules so their classes are registered on Base.metadata
    before autogenerate runs (without this, tables would appear as "dropped").
  - Reads SYNC_DATABASE_URL from settings — never hard-codes credentials.
  - Enables compare_type=True so column type changes are detected.
"""

import sys
from logging.config import fileConfig
from pathlib import Path

# ── Path Setup ────────────────────────────────────────────────────────────────
# Make sure `from app.xxx import yyy` works when Alembic runs from backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from alembic import context
from sqlalchemy import engine_from_config, pool

# ── Import Base and ALL Models ────────────────────────────────────────────────
# CRITICAL: Every model module must be imported here so that SQLAlchemy
# registers the table metadata on Base before autogenerate compares it.
from app.config.settings import settings
from app.db.base import Base
from app.db import models  # noqa: F401 — side-effect import, registers all tables

# ── Alembic Config ────────────────────────────────────────────────────────────
config = context.config

# Override the SQLAlchemy URL with the value from settings (respects .env)
config.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URL)

# Set up stdlib logging from alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata object that autogenerate will compare against the live DB
target_metadata = Base.metadata


# ── Migration Functions ───────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """
    Run migrations in 'offline' mode.

    In offline mode, Alembic generates SQL statements to stdout or a file
    without connecting to the database. Useful for DBAs who need to review
    SQL before applying it.

    Triggered by: alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,          # detect column type changes
        compare_server_default=True,# detect server default changes
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in 'online' mode (standard).

    In online mode, Alembic connects to the DB, acquires a transaction,
    runs the migration, and commits. Failures automatically rollback.

    Note: We use psycopg2 (sync driver) here — asyncpg cannot be used
    by Alembic because Alembic's migration runner is synchronous.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,    # don't pool in migration scripts
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            # Include schemas if using PostgreSQL schemas beyond 'public'
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


# ── Entry Point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
