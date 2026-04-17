"""
Query API — read side.

Reads are served from the in-memory projected state (or trigger a replay if
state is empty — i.e., after a simulated crash).

Endpoints:
  GET /state                → full ledger state
  GET /state/{account_id}   → single account
  GET /events/{stream_id}   → raw event log for a stream
  GET /replay               → trigger/return replay result
  GET /validate             → run validation layer against current state
  GET /streams              → list all known account streams
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.engine import event_store as es
from app.engine.replay import replay_from_snapshot, replay_full
from app.engine.validator import validate_ledger

router = APIRouter(prefix="/queries", tags=["Queries"])


# ─────────────────────────────────────────────────────────────
# State
# ─────────────────────────────────────────────────────────────

@router.get("/state")
def get_full_state():
    """Replay and return the full ledger state."""
    ledger, metrics = replay_full(save_snap=True)
    return {
        "state": ledger.to_dict(),
        "metrics": metrics.to_dict(),
    }


@router.get("/state/{account_id}")
def get_account_state(account_id: str):
    """Return state of a single account via targeted stream replay."""
    stream_id = _full_stream_id(account_id)
    from app.engine.projector import ProjectorSession

    events = list(es.read_stream(stream_id))
    if not events:
        raise HTTPException(404, f"Account {account_id} not found or has no events")

    session = ProjectorSession()
    for ev in events:
        session.apply(ev)

    acc = session.ledger.accounts.get(stream_id)
    if acc is None:
        raise HTTPException(404, f"Account {account_id} not found in state")

    return acc.to_dict()


# ─────────────────────────────────────────────────────────────
# Events
# ─────────────────────────────────────────────────────────────

@router.get("/events/{account_id}")
def get_events(account_id: str):
    """Return raw event log for an account stream."""
    stream_id = _full_stream_id(account_id)
    events = list(es.read_stream(stream_id))
    if not events:
        raise HTTPException(404, f"No events found for {account_id}")

    return {
        "stream_id": stream_id,
        "event_count": len(events),
        "events": [e.model_dump() for e in events],
    }


@router.get("/streams")
def list_streams():
    """List all account streams."""
    streams = es.list_streams_with_prefix("account-")
    return {"streams": streams, "count": len(streams)}


# ─────────────────────────────────────────────────────────────
# Replay
# ─────────────────────────────────────────────────────────────

@router.get("/replay")
def trigger_replay(
    mode: str = Query(default="full", enum=["full", "snapshot"]),
    until: Optional[str] = Query(default=None, description="ISO-8601 UTC datetime for time-travel"),
):
    """
    Trigger a full or snapshot-assisted replay.

    Optional `until` param enables time-travel: rebuild state as of a past moment.
    """
    until_dt: datetime | None = None
    if until:
        try:
            until_dt = datetime.fromisoformat(until)
        except ValueError:
            raise HTTPException(400, f"Invalid datetime: {until}")

    if mode == "snapshot":
        ledger, metrics = replay_from_snapshot(until=until_dt)
    else:
        ledger, metrics = replay_full(until=until_dt, save_snap=True)

    validation = validate_ledger(ledger)

    return {
        "state": ledger.to_dict(),
        "metrics": metrics.to_dict(),
        "validation": validation.to_dict(),
    }


# ─────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────

@router.get("/validate")
def validate():
    """Run the validation layer against the current replayed state."""
    ledger, metrics = replay_full(save_snap=False)
    report = validate_ledger(ledger)
    return {
        "validation": report.to_dict(),
        "metrics": metrics.to_dict(),
    }


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _full_stream_id(account_id: str) -> str:
    prefix = "account-"
    if account_id.startswith(prefix):
        return account_id
    return f"{prefix}{account_id}"
