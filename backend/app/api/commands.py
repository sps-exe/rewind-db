"""
Command API — write side of the ledger.

All writes go through Events, never directly to state.
Each endpoint:
  1. Validates the request (Pydantic)
  2. Resolves the current stream version (for optimistic concurrency)
  3. Constructs the domain event
  4. Appends to EventStoreDB
  5. Returns confirmation (NOT the mutated state — clients must query separately)

This enforces write/read separation (CQRS lite).
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.domain.events import (
    AccountCreated,
    AccountFrozen,
    MoneyDeposited,
    MoneyWithdrawn,
    TransferInitiated,
    TransferReceived,
)
from app.engine import event_store as es

router = APIRouter(prefix="/commands", tags=["Commands"])

STREAM_PREFIX = "account-"


def _next_version(stream_id: str) -> int:
    """Compute the next expected version by counting existing events."""
    return sum(1 for _ in es.read_stream(stream_id))


# ─────────────────────────────────────────────────────────────
# Request schemas
# ─────────────────────────────────────────────────────────────

class CreateAccountRequest(BaseModel):
    owner: str = Field(..., min_length=1)
    initial_balance: float = Field(default=0.0, ge=0.0)
    account_id: Optional[str] = Field(default=None, description="Optional custom ID")


class DepositRequest(BaseModel):
    amount: float = Field(..., gt=0)


class WithdrawRequest(BaseModel):
    amount: float = Field(..., gt=0)


class TransferRequest(BaseModel):
    amount: float = Field(..., gt=0)
    target_account_id: str


class FreezeRequest(BaseModel):
    reason: str = Field(default="Administrative freeze")


# ─────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────

@router.post("/accounts", status_code=201)
def create_account(body: CreateAccountRequest):
    account_id = f"{STREAM_PREFIX}{body.account_id or str(uuid.uuid4())[:8]}"
    version = _next_version(account_id)
    if version > 0:
        raise HTTPException(409, f"Account {account_id} already exists")

    event = AccountCreated(
        stream_id=account_id,
        version=0,
        owner=body.owner,
        initial_balance=body.initial_balance,
    )
    try:
        es.append_event(event)
    except Exception as exc:
        raise HTTPException(500, f"Failed to create account: {exc}") from exc

    return {"account_id": account_id, "event_id": event.event_id, "version": 0}


@router.post("/accounts/{account_id}/deposit", status_code=201)
def deposit(account_id: str, body: DepositRequest):
    stream_id = _full_stream_id(account_id)
    version = _next_version(stream_id)
    if version == 0:
        raise HTTPException(404, f"Account {account_id} not found")

    event = MoneyDeposited(stream_id=stream_id, version=version, amount=body.amount)
    try:
        es.append_event(event)
    except Exception as exc:
        raise HTTPException(500, f"Deposit failed: {exc}") from exc

    return {"event_id": event.event_id, "version": version}


@router.post("/accounts/{account_id}/withdraw", status_code=201)
def withdraw(account_id: str, body: WithdrawRequest):
    stream_id = _full_stream_id(account_id)
    events = list(es.read_stream(stream_id))
    if not events:
        raise HTTPException(404, f"Account {account_id} not found")

    # Quick balance check before appending (optimistic read)
    from app.engine.projector import ProjectorSession
    session = ProjectorSession()
    for ev in events:
        session.apply(ev)
    acc = session.ledger.accounts.get(stream_id)
    if acc is None or acc.balance < body.amount:
        raise HTTPException(400, f"Insufficient funds: balance={acc.balance if acc else 0}")

    event = MoneyWithdrawn(stream_id=stream_id, version=len(events), amount=body.amount)
    try:
        es.append_event(event)
    except Exception as exc:
        raise HTTPException(500, f"Withdrawal failed: {exc}") from exc

    return {"event_id": event.event_id, "version": event.version}


@router.post("/accounts/{account_id}/transfer", status_code=201)
def transfer(account_id: str, body: TransferRequest):
    src_stream = _full_stream_id(account_id)
    tgt_stream = _full_stream_id(body.target_account_id)

    src_events = list(es.read_stream(src_stream))
    tgt_events = list(es.read_stream(tgt_stream))

    if not src_events:
        raise HTTPException(404, f"Source account {account_id} not found")
    if not tgt_events:
        raise HTTPException(404, f"Target account {body.target_account_id} not found")

    # Balance check
    from app.engine.projector import ProjectorSession
    session = ProjectorSession()
    for ev in src_events:
        session.apply(ev)
    acc = session.ledger.accounts.get(src_stream)
    if acc is None or acc.balance < body.amount:
        raise HTTPException(400, f"Insufficient funds: {acc.balance if acc else 0}")

    correlation_id = str(uuid.uuid4())

    ev_debit = TransferInitiated(
        stream_id=src_stream,
        version=len(src_events),
        amount=body.amount,
        target_account_id=tgt_stream,
        correlation_id=correlation_id,
    )
    ev_credit = TransferReceived(
        stream_id=tgt_stream,
        version=len(tgt_events),
        amount=body.amount,
        source_account_id=src_stream,
        correlation_id=correlation_id,
    )

    try:
        es.append_event(ev_debit)
        es.append_event(ev_credit)
    except Exception as exc:
        raise HTTPException(500, f"Transfer failed: {exc}") from exc

    return {
        "correlation_id": correlation_id,
        "debit_event_id": ev_debit.event_id,
        "credit_event_id": ev_credit.event_id,
    }


@router.post("/accounts/{account_id}/freeze", status_code=201)
def freeze_account(account_id: str, body: FreezeRequest):
    stream_id = _full_stream_id(account_id)
    version = _next_version(stream_id)
    if version == 0:
        raise HTTPException(404, f"Account {account_id} not found")

    event = AccountFrozen(stream_id=stream_id, version=version, reason=body.reason)
    try:
        es.append_event(event)
    except Exception as exc:
        raise HTTPException(500, f"Freeze failed: {exc}") from exc

    return {"event_id": event.event_id, "version": version}


def _full_stream_id(account_id: str) -> str:
    if account_id.startswith(STREAM_PREFIX):
        return account_id
    return f"{STREAM_PREFIX}{account_id}"
