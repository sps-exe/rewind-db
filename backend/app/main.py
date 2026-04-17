"""
RewindDB FastAPI Application

Entrypoint that wires together:
  - CORS (all origins allowed for hackathon)
  - Command API (write side)
  - Query API (read side)
  - Simulation API (chaos + demo)
  - Health check

Architecture note:
  There is intentionally NO in-process shared state variable for the ledger.
  Every query triggers a replay. This is the core proof:
  "State is reconstructed purely from the event log on every read."

  In a production system you'd cache the projected state in Redis / a
  read-model DB and update it via subscriptions. For this demo, re-replay
  takes < 10ms for a small event log and proves the concept clearly.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.commands import router as commands_router
from app.api.queries import router as queries_router
from app.api.simulation import router as simulation_router

app = FastAPI(
    title="RewindDB",
    description=(
        "State recovery system proving that State = f(Events). "
        "Built on EventStoreDB for the Zero-to-One Hackathon."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(commands_router)
app.include_router(queries_router)
app.include_router(simulation_router)


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    """Quick liveness check."""
    return {"status": "ok", "service": "RewindDB"}


@app.get("/", tags=["System"])
def root():
    return {
        "service": "RewindDB",
        "tagline": "State is a pure function of events.",
        "docs": "/docs",
        "endpoints": {
            "commands": "/commands",
            "queries": "/queries",
            "simulate": "/simulate",
            "health": "/health",
        },
    }
