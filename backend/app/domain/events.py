"""
Domain Events — the immutable facts that happened.

Every event has:
  - event_id    : uuid4 string  (idempotency key)
  - stream_id   : which account stream this belongs to
  - version     : optimistic-concurrency sequence number
  - timestamp   : ISO-8601 UTC
  - type        : discriminated-union tag

Design choice: plain Pydantic models with a `type` literal field.
EventStoreDB stores the raw JSON; we deserialize via `EVENT_MAP`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────

class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=_uid)
    stream_id: str          # e.g. "account-abc123"
    version: int            # 0-based position expected in the stream
    occurred_at: datetime = Field(default_factory=_now)

    model_config = {"frozen": True}


# ─────────────────────────────────────────────────────────────
# Concrete events
# ─────────────────────────────────────────────────────────────

class AccountCreated(BaseEvent):
    type: Literal["AccountCreated"] = "AccountCreated"
    owner: str
    initial_balance: float


class MoneyDeposited(BaseEvent):
    type: Literal["MoneyDeposited"] = "MoneyDeposited"
    amount: float


class MoneyWithdrawn(BaseEvent):
    type: Literal["MoneyWithdrawn"] = "MoneyWithdrawn"
    amount: float


class TransferInitiated(BaseEvent):
    """Debit side of a transfer (paired with TransferReceived on target)."""
    type: Literal["TransferInitiated"] = "TransferInitiated"
    amount: float
    target_account_id: str
    correlation_id: str = Field(default_factory=_uid)


class TransferReceived(BaseEvent):
    """Credit side of a transfer."""
    type: Literal["TransferReceived"] = "TransferReceived"
    amount: float
    source_account_id: str
    correlation_id: str


class AccountFrozen(BaseEvent):
    type: Literal["AccountFrozen"] = "AccountFrozen"
    reason: str


# ─────────────────────────────────────────────────────────────
# Discriminated union — used for deserialization
# ─────────────────────────────────────────────────────────────

DomainEvent = Annotated[
    Union[
        AccountCreated,
        MoneyDeposited,
        MoneyWithdrawn,
        TransferInitiated,
        TransferReceived,
        AccountFrozen,
    ],
    Field(discriminator="type"),
]

# Map event type-string → class (used by event store client decoder)
EVENT_MAP: dict[str, type[BaseEvent]] = {
    "AccountCreated": AccountCreated,
    "MoneyDeposited": MoneyDeposited,
    "MoneyWithdrawn": MoneyWithdrawn,
    "TransferInitiated": TransferInitiated,
    "TransferReceived": TransferReceived,
    "AccountFrozen": AccountFrozen,
}
