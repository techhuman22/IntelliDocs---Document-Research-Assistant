#!/bin/bash
# Production startup script for Render
# 1. Run database migrations
# 2. Start the FastAPI server

set -e

echo "🔄 Running database migrations..."
python -m alembic upgrade head
echo "✅ Migrations complete"

echo "🚀 Starting FastAPI server..."
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "${PORT:-8000}" \
    --workers 1 \
    --loop uvloop \
    --http httptools
