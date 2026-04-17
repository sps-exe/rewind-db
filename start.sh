#!/bin/bash
# RewindDB — one-shot startup script
# Usage: ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 RewindDB Startup"
echo "==================="

# 1. Start EventStoreDB
echo "→ Starting EventStoreDB via Docker..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo "→ Waiting for EventStoreDB to be ready..."
for i in {1..20}; do
  if curl -s http://localhost:2113/health/live >/dev/null 2>&1; then
    echo "✅ EventStoreDB is up!"
    break
  fi
  echo "  Waiting... ($i/20)"
  sleep 2
done

# 2. Start FastAPI backend
echo "→ Starting RewindDB backend..."
cd "$SCRIPT_DIR/backend"

if [ ! -d ".venv" ]; then
  echo "  Creating virtual environment..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt -q
else
  source .venv/bin/activate
fi

mkdir -p data/snapshots

echo "✅ Backend starting on http://localhost:8001"
echo "📚 API Docs: http://localhost:8001/docs"
echo ""

uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
