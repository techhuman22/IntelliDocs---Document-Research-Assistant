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


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
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

# Copy application code
COPY --chown=appuser:appuser . .

# Create uploads directory with correct ownership
RUN mkdir -p /app/uploads && chown appuser:appuser /app/uploads

USER appuser

# Expose the application port
EXPOSE 8000

# Health check — Docker will mark the container unhealthy if this fails
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Production command — 4 workers, no reload
# Override this in docker-compose.yml for development (add --reload)
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools"]
