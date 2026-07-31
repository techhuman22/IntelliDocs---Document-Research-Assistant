# ── Stage 1: Builder ──────────────────────────────────────────────────────────
# Install dependencies in a separate stage to keep the final image lean.
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies (needed for some compiled packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer cache.
# If requirements.txt hasn't changed, pip install is skipped on rebuild.
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt


# ── Stage 2: Model Download ──────────────────────────────────────────────────
# Pre-download the HuggingFace embedding model during build using the standard
# HF hub cache layout.  Using all-MiniLM-L6-v2 (~80 MB, 384-dim) instead of
# all-mpnet-base-v2 (~420 MB, 768-dim) to fit Render free-tier memory (512 MB).
FROM python:3.11-slim AS model-downloader

COPY --from=builder /install /usr/local

# Setting HF_HOME makes the download land in /models/hub/models--sentence-transformers--...
ENV HF_HOME=/models

RUN python -c "\
from sentence_transformers import SentenceTransformer; \
SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"


# ── Stage 3: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Create non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --no-create-home appuser

WORKDIR /app

# Runtime system dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder stage
COPY --from=builder /install /usr/local

# Copy pre-downloaded model WITH correct ownership so appuser can write
# lock files and metadata at runtime (this was the PermissionError cause)
COPY --chown=appuser:appuser --from=model-downloader /models /app/models

# Copy application code
COPY --chown=appuser:appuser . .

# Make start script executable
RUN chmod +x /app/start.sh

# Create uploads directory with correct ownership
RUN mkdir -p /app/uploads && chown appuser:appuser /app/uploads

# Point all HF/ST cache env vars to the pre-downloaded location
ENV HF_HOME=/app/models
ENV SENTENCE_TRANSFORMERS_HOME=/app/models
ENV TRANSFORMERS_CACHE=/app/models

USER appuser

# Expose the application port
EXPOSE 8000

# Health check — Docker will mark the container unhealthy if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Use start.sh which runs migrations then starts the server
CMD ["/bin/bash", "/app/start.sh"]
