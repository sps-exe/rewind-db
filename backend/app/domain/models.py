"""
State Models — the current snapshot of an account.

Design rationale:
  State is derived ONLY from events. We never mutate state directly;
  every mutation goes through the projector by appending an event first.

AccountState is intentionally a mutable dataclass (not Pydantic)
because the projector mutates it in a tight loop during replay.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class AccountStatus(str, Enum):
    ACTIVE = "active"
    FROZEN = "frozen"


@dataclass
class AccountState:
    account_id: str
    owner: str
    balance: float = 0.0
    status: AccountStatus = AccountStatus.ACTIVE
    version: int = -1          # last applied event version
    event_count: int = 0       # total events applied (for diagnostics)
    created_at: datetime | None = None
    last_updated: datetime | None = None

    def to_dict(self) -> dict:
        return {
            "account_id": self.account_id,
            "owner": self.owner,
            "balance": round(self.balance, 2),
            "status": self.status.value,
            "version": self.version,
            "event_count": self.event_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
        }


@dataclass
class LedgerState:
    """Aggregated view across all accounts — used for global validation checks."""
    accounts: dict[str, AccountState] = field(default_factory=dict)
    total_events_processed: int = 0
    replay_source: str = "full"   # "full" | "snapshot"

    def to_dict(self) -> dict:
        return {
            "accounts": {k: v.to_dict() for k, v in self.accounts.items()},
            "total_events_processed": self.total_events_processed,
            "replay_source": self.replay_source,
            "account_count": len(self.accounts),
        }
