"""
Deterministic Projector — the core of RewindDB.

A projector is a pure function:
    apply(current_state, event) → new_state

Key properties enforced here:
  1. DETERMINISM   — same events always produce the same state.
                     Achieved by: no randomness, no side-effects, no wall-clock
                     reads inside apply().  Time comes from the event itself.
  2. IDEMPOTENCY   — applying the same event_id twice has no extra effect.
                     Achieved by: `_seen` set tracked per-replay session.
  3. ORDERING      — events must arrive in strict version order.
                     Achieved by: version gap detection with explicit error.
  4. COMPLETENESS  — every event type has a handler; unknown events raise.

Design:
  ProjectorSession is created fresh for each replay run. No shared mutable state
  leaks between sessions — guaranteeing determinism across repeated replays.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.domain.events import (
    AccountCreated,
    AccountFrozen,
    BaseEvent,
    MoneyDeposited,
    MoneyWithdrawn,
    TransferInitiated,
    TransferReceived,
)
from app.domain.models import AccountState, AccountStatus, LedgerState

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────

class OrderingViolation(Exception):
    """Raised when an event arrives out of sequence."""


class UnknownEventType(Exception):
    """Raised when the projector receives an event it cannot handle."""


class InsufficientFunds(Exception):
    """Raised during apply if a withdrawal would make balance negative."""


class AccountNotFound(Exception):
    pass


class AccountAlreadyFrozen(Exception):
    pass


# ─────────────────────────────────────────────────────────────
# Projector Session
# ─────────────────────────────────────────────────────────────

@dataclass
class ProjectorSession:
    """
    Stateful session for a single replay run.

    Usage:
        session = ProjectorSession()
        for event in events:
            session.apply(event)
        state = session.ledger
    """

    ledger: LedgerState = field(default_factory=LedgerState)

    # per-stream version tracking for ordering enforcement
    _stream_versions: dict[str, int] = field(default_factory=dict)
    # seen event_ids for idempotency
    _seen: set[str] = field(default_factory=set)

    def apply(self, event: BaseEvent) -> None:
        """Apply a single event to the projector session."""

        # ── Idempotency guard ──────────────────────────────────────────────
        if event.event_id in self._seen:
            logger.warning(
                "DUPLICATE detected — event_id=%s type=%s — skipping",
                event.event_id,
                event.type,  # type: ignore[attr-defined]
            )
            return

        # ── Ordering guard ─────────────────────────────────────────────────
        expected_version = self._stream_versions.get(event.stream_id, -1) + 1
        if event.version != expected_version:
            raise OrderingViolation(
                f"Stream {event.stream_id}: expected version {expected_version}, "
                f"got {event.version}. Out-of-order delivery detected."
            )

        # ── Dispatch ───────────────────────────────────────────────────────
        handler = _HANDLERS.get(type(event))
        if handler is None:
            raise UnknownEventType(f"No handler for {type(event).__name__}")

        handler(self.ledger, event)

        # ── Bookkeeping ────────────────────────────────────────────────────
        self._seen.add(event.event_id)
        self._stream_versions[event.stream_id] = event.version
        self.ledger.total_events_processed += 1


# ─────────────────────────────────────────────────────────────
# Per-event handlers (pure functions)
# ─────────────────────────────────────────────────────────────

def _apply_account_created(ledger: LedgerState, ev: AccountCreated) -> None:
    account = AccountState(
        account_id=ev.stream_id,
        owner=ev.owner,
        balance=ev.initial_balance,
        created_at=ev.occurred_at,
        last_updated=ev.occurred_at,
        version=ev.version,
        event_count=1,
    )
    ledger.accounts[ev.stream_id] = account


def _apply_money_deposited(ledger: LedgerState, ev: MoneyDeposited) -> None:
    account = _require_account(ledger, ev.stream_id)
    _require_active(account)
    account.balance += ev.amount
    account.version = ev.version
    account.event_count += 1
    account.last_updated = ev.occurred_at


def _apply_money_withdrawn(ledger: LedgerState, ev: MoneyWithdrawn) -> None:
    account = _require_account(ledger, ev.stream_id)
    _require_active(account)
    if account.balance < ev.amount:
        raise InsufficientFunds(
            f"Account {ev.stream_id} has {account.balance:.2f}, "
            f"cannot withdraw {ev.amount:.2f}"
        )
    account.balance -= ev.amount
    account.version = ev.version
    account.event_count += 1
    account.last_updated = ev.occurred_at


def _apply_transfer_initiated(ledger: LedgerState, ev: TransferInitiated) -> None:
    account = _require_account(ledger, ev.stream_id)
    _require_active(account)
    if account.balance < ev.amount:
        raise InsufficientFunds(
            f"Account {ev.stream_id} has {account.balance:.2f}, "
            f"cannot transfer {ev.amount:.2f}"
        )
    account.balance -= ev.amount
    account.version = ev.version
    account.event_count += 1
    account.last_updated = ev.occurred_at


def _apply_transfer_received(ledger: LedgerState, ev: TransferReceived) -> None:
    account = _require_account(ledger, ev.stream_id)
    _require_active(account)
    account.balance += ev.amount
    account.version = ev.version
    account.event_count += 1
    account.last_updated = ev.occurred_at


def _apply_account_frozen(ledger: LedgerState, ev: AccountFrozen) -> None:
    account = _require_account(ledger, ev.stream_id)
    account.status = AccountStatus.FROZEN
    account.version = ev.version
    account.event_count += 1
    account.last_updated = ev.occurred_at


# ─────────────────────────────────────────────────────────────
# Handler dispatch table
# ─────────────────────────────────────────────────────────────

_HANDLERS = {
    AccountCreated: _apply_account_created,
    MoneyDeposited: _apply_money_deposited,
    MoneyWithdrawn: _apply_money_withdrawn,
    TransferInitiated: _apply_transfer_initiated,
    TransferReceived: _apply_transfer_received,
    AccountFrozen: _apply_account_frozen,
}


# ─────────────────────────────────────────────────────────────
# Helper guards
# ─────────────────────────────────────────────────────────────

def _require_account(ledger: LedgerState, account_id: str) -> AccountState:
    acc = ledger.accounts.get(account_id)
    if acc is None:
        raise AccountNotFound(f"Account {account_id} not found in projected state.")
    return acc


def _require_active(account: AccountState) -> None:
    if account.status != AccountStatus.ACTIVE:
        raise AccountAlreadyFrozen(
            f"Account {account.account_id} is frozen and cannot accept transactions."
        )
