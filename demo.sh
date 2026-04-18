#!/bin/bash
# RewindDB — Hackathon Demo Launcher
# Starts EventStoreDB + Backend + Serveo tunnel in one command
# Usage: ./demo.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════╗"
echo "║       RewindDB — Hackathon Demo          ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ── 1. Start EventStoreDB ─────────────────────────────────────
echo "→ Starting EventStoreDB..."
docker compose -f "$SCRIPT_DIR/docker-compose.yml" up -d

echo "→ Waiting for EventStoreDB..."
for i in {1..20}; do
  if curl -s http://localhost:2113/health/live > /dev/null 2>&1; then
    echo "✅ EventStoreDB is ready!"
    break
  fi
  echo "   ($i/20) still starting..."
  sleep 3
done

# ── 2. Start FastAPI backend (background) ────────────────────
echo ""
echo "→ Starting FastAPI backend on port 8001..."
cd "$SCRIPT_DIR/backend"

if [ ! -d ".venv" ]; then
  echo "   Creating virtualenv..."
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt -q
else
  source .venv/bin/activate
fi

mkdir -p data/snapshots
uvicorn app.main:app --host 0.0.0.0 --port 8001 > /tmp/rewinddb-backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"

sleep 3

if curl -s http://localhost:8001/health > /dev/null 2>&1; then
  echo "✅ Backend is up at http://localhost:8001"
else
  echo "❌ Backend failed to start. Check /tmp/rewinddb-backend.log"
  cat /tmp/rewinddb-backend.log
  exit 1
fi

# ── 3. Start Serveo tunnel ────────────────────────────────────
echo ""
echo "→ Opening Serveo tunnel for port 8001..."
echo "   (Serveo will print your public URL below)"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  COPY the https://....serveo.net URL below"
echo "  Then run: ./update-url.sh <that-url>"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Keep tunnel alive with autossh-style reconnect
while true; do
  ssh -o StrictHostKeyChecking=no \
      -o ServerAliveInterval=30 \
      -o ServerAliveCountMax=3 \
      -o ExitOnForwardFailure=yes \
      -R 80:localhost:8001 \
      serveo.net 2>&1 || true
  echo "⚠️  Tunnel dropped — reconnecting in 3s..."
  sleep 3
done
