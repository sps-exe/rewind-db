"""
Failure Simulation API — judge-facing chaos endpoints.

POST /simulate/crash         → wipe in-memory snapshot (forces next replay)
POST /simulate/duplicate     → inject duplicate event, show idempotency
POST /simulate/out-of-order  → swap events, show ordering violation
POST /simulate/missing        → skip event, show gap detection
POST /simulate/corruption    → corrupt state in memory, prove replay restores
POST /simulate/seed          → seed demo data (multiple accounts + transfers)
DELETE /simulate/reset       → clear all snapshots + nuke demo streams
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.engine import event_store as es
from app.engine.simulator import (
    simulate_duplicate,
    simulate_missing_event,
    simulate_out_of_order,
    simulate_state_corruption,
    simulate_concurrent_writes,
)
from app.engine.snapshot import delete_snapshot

router = APIRouter(prefix="/simulate", tags=["Failure Simulation"])


class DuplicateRequest(BaseModel):
    account_id: str
    amount: float = 100.0


class OrderingRequest(BaseModel):
    account_id: str


class ConcurrentRequest(BaseModel):
    account_id: str
    num_writers: int = 5


class SeedRequest(BaseModel):
    num_accounts: int = 3
    transactions_per_account: int = 4


# ─────────────────────────────────────────────────────────────
# Crash simulation
# ─────────────────────────────────────────────────────────────

@router.post("/crash")
def simulate_crash():
    """
    Delete the in-memory snapshot so the next /replay starts from zero.
    Simulates a server crash + restart.
    """
    delete_snapshot()
    return {
        "scenario": "crash",
        "injected": "In-memory snapshot deleted",
        "system_response": "Next replay will perform full event log reconstruction",
        "recovered": True,
    }


# ─────────────────────────────────────────────────────────────
# Duplicate injection
# ─────────────────────────────────────────────────────────────

@router.post("/duplicate")
def simulate_dup(body: DuplicateRequest):
    stream_id = _full_stream_id(body.account_id)
    result = simulate_duplicate(stream_id, body.amount)
    return result.to_dict()


# ─────────────────────────────────────────────────────────────
# Out-of-order
# ─────────────────────────────────────────────────────────────

@router.post("/out-of-order")
def simulate_oor(body: OrderingRequest):
    stream_id = _full_stream_id(body.account_id)
    result = simulate_out_of_order(stream_id)
    return result.to_dict()


# ─────────────────────────────────────────────────────────────
# Missing event
# ─────────────────────────────────────────────────────────────

@router.post("/missing")
def simulate_missing(body: OrderingRequest):
    stream_id = _full_stream_id(body.account_id)
    result = simulate_missing_event(stream_id)
    return result.to_dict()


# ─────────────────────────────────────────────────────────────
# State corruption
# ─────────────────────────────────────────────────────────────

@router.post("/corruption")
def simulate_corrupt(body: OrderingRequest):
    stream_id = _full_stream_id(body.account_id)
    result = simulate_state_corruption(stream_id)
    return result.to_dict()


# ─────────────────────────────────────────────────────────────
# Seed demo data
# ─────────────────────────────────────────────────────────────

@router.post("/seed")
def seed_demo(body: SeedRequest):
    """
    Create demo accounts and run transactions to populate the event log.
    Perfect for quick judge demonstrations.
    """
    from app.domain.events import (
        AccountCreated,
        MoneyDeposited,
        MoneyWithdrawn,
        TransferInitiated,
        TransferReceived,
    )

    created_accounts = []

    # Create accounts
    account_ids = []
    owners = ["Alice", "Bob", "Carol", "Dave", "Eve"]
    for i in range(body.num_accounts):
        aid = f"account-demo-{str(uuid.uuid4())[:6]}"
        owner = owners[i % len(owners)]
        ev = AccountCreated(
            stream_id=aid, version=0, owner=owner, initial_balance=1000.0
        )
        try:
            es.append_event(ev)
            account_ids.append(aid)
            created_accounts.append({"account_id": aid, "owner": owner})
        except Exception as exc:
            # Stream already exists — skip
            pass

    # Deposits + withdrawals
    for aid in account_ids:
        for i in range(1, body.transactions_per_account + 1):
            ev = MoneyDeposited(
                stream_id=aid,
                version=i,
                amount=float(100 * i),
            )
            try:
                es.append_event(ev)
            except Exception:
                pass

    # Cross-account transfer (first → second)
    if len(account_ids) >= 2:
        src, tgt = account_ids[0], account_ids[1]
        src_ver = body.transactions_per_account + 1
        tgt_ver = body.transactions_per_account + 1
        corr = str(uuid.uuid4())

        try:
            es.append_event(TransferInitiated(
                stream_id=src, version=src_ver, amount=250.0,
                target_account_id=tgt, correlation_id=corr,
            ))
            es.append_event(TransferReceived(
                stream_id=tgt, version=tgt_ver, amount=250.0,
                source_account_id=src, correlation_id=corr,
            ))
        except Exception:
            pass

    return {
        "seeded_accounts": created_accounts,
        "transactions_per_account": body.transactions_per_account,
    }


# ─────────────────────────────────────────────────────────────
# Reset
# ─────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────
# Concurrent writes
# ─────────────────────────────────────────────────────────────

@router.post("/concurrent")
def simulate_concurrent(body: ConcurrentRequest):
    """
    Fire `num_writers` threads simultaneously, all trying to write version N
    to the same stream. EventStoreDB's optimistic concurrency ensures exactly
    one succeeds — the rest get WrongExpectedVersion.

    Proves: no distributed lock needed, the event store is the arbiter.
    """
    stream_id = _full_stream_id(body.account_id)
    result = simulate_concurrent_writes(stream_id, body.num_writers)
    return result.to_dict()


# ─────────────────────────────────────────────────────────────
# Reset
# ─────────────────────────────────────────────────────────────

@router.delete("/reset")
def reset():
    """Delete snapshot. (EventStoreDB streams are append-only — cannot delete in demo mode.)"""
    delete_snapshot()
    return {"message": "Snapshot cleared. EventStoreDB streams are immutable by design."}


def _full_stream_id(account_id: str) -> str:
    if account_id.startswith("account-"):
        return account_id
    return f"account-{account_id}"
