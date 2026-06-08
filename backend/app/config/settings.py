"""
Application configuration via Pydantic Settings v2.

All values are read from environment variables or the .env file.
Access the singleton via: from app.config.settings import settings
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, EmailStr, Field, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration object. All fields map 1-to-1 with .env keys."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",             # ignore unknown env vars — safe for Docker
    )

    # ── Application ──────────────────────────────────────────────────────────
    APP_NAME: str = "AgentFlow AI"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    SECRET_KEY: str = Field(min_length=32)

    # ── Server ────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 1
    RELOAD: bool = True

    # ── PostgreSQL (individual components) ───────────────────────────────────
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "agentflow"
    POSTGRES_USER: str = "agentflow_user"
    POSTGRES_PASSWORD: str

    # Derived — constructed in model_validator below
    DATABASE_URL: str = ""          # async URL  (asyncpg)
    SYNC_DATABASE_URL: str = ""     # sync URL   (psycopg2, used by Alembic)

    # SQLAlchemy engine options
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30       # seconds before giving up on a connection
    DB_POOL_RECYCLE: int = 1800     # recycle connections every 30 minutes
    DB_ECHO: bool = False           # set True to log all SQL (dev only)

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: str = ""

    REDIS_URL: str = ""             # derived in model_validator

    # ── JWT ───────────────────────────────────────────────────────────────────
    JWT_SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Groq API ──────────────────────────────────────────────────────────────
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_FAST_MODEL: str = "llama-3.1-8b-instant"   # used for routing (cheaper/faster)

    # ── HuggingFace Embeddings (local, no API key needed) ─────────────────────
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-mpnet-base-v2"
    EMBEDDING_DIMENSION: int = 768

    # ── File Upload ───────────────────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_EXTENSIONS: str = "pdf,docx,txt"
    UPLOAD_DIR: str = "./uploads"

    # ── RAG / Chunking ────────────────────────────────────────────────────────
    CHUNK_SIZE: int = 512               # target tokens per chunk
    CHUNK_OVERLAP: int = 64             # overlap between adjacent chunks (tokens)
    RETRIEVAL_TOP_K: int = 8            # chunks returned per similarity search
    RETRIEVAL_SIMILARITY_THRESHOLD: float = 0.70  # min cosine score to include

    # Embedding batching — sentence-transformers processes locally in batches
    EMBEDDING_BATCH_SIZE: int = 64

    # Retry config for LLM API calls (exponential backoff)
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_DELAY: float = 1.0    # initial delay in seconds

    # Context building
    CONTEXT_MAX_TOKENS: int = 8000     # max tokens to include in built context
    CONTEXT_SEPARATOR: str = "\n\n---\n\n"  # separator between chunks in context

    # ── Celery ────────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── CORS ──────────────────────────────────────────────────────────────────
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002"

    # ── Rate Limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW_SECONDS: int = 60

    # ── Logging ───────────────────────────────────────────────────────────────
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG"
    LOG_FORMAT: Literal["json", "console"] = "json"
    LOG_FILE: str = ""

    # ── External APIs (later phases) ─────────────────────────────────────────
    TAVILY_API_KEY: str = ""

    # ─────────────────────────────────────────────────────────────────────────
    # Derived fields — built automatically from the individual components
    # ─────────────────────────────────────────────────────────────────────────

    @model_validator(mode="after")
    def _assemble_urls(self) -> "Settings":
        """Build connection URLs from individual components if not overridden."""

        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        if not self.SYNC_DATABASE_URL:
            self.SYNC_DATABASE_URL = (
                f"postgresql+psycopg2://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

        if not self.REDIS_URL:
            auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
            self.REDIS_URL = (
                f"redis://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
            )

        return self

    # ─────────────────────────────────────────────────────────────────────────
    # Computed helpers
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def allowed_extensions_list(self) -> list[str]:
        return [ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",")]

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT == "development"

    @property
    def upload_dir_path(self) -> Path:
        path = Path(self.UPLOAD_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.

    Using @lru_cache ensures .env is read exactly once at startup.
    In tests, call get_settings.cache_clear() to reset between tests.
    """
    return Settings()


# Module-level singleton — import this everywhere
settings: Settings = get_settings()
