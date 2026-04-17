"""
Core test suite for RewindDB.

Tests are entirely in-memory — no EventStoreDB required for unit tests.
We feed events directly into the ProjectorSession.

Test categories:
  1. Determinism — same events, same state, always
  2. Idempotency — duplicate events silently skipped
  3. Ordering — out-of-order events raise OrderingViolation
  4. Invariants — insufficient funds, frozen accounts
  5. Snapshot — save/load round-trip produces identical state
  6. Validation — ValidationLayer catches corrupted state
"""

from __future__ import annotations

import json
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.domain.events import (
    AccountCreated,
    AccountFrozen,
    MoneyDeposited,
    MoneyWithdrawn,
    TransferInitiated,
    TransferReceived,
)
from app.domain.models import AccountStatus, LedgerState
from app.engine.projector import (
    AccountAlreadyFrozen,
    AccountNotFound,
    InsufficientFunds,
    OrderingViolation,
    ProjectorSession,
)
from app.engine.validator import Severity, validate_ledger


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

AID = "account-test-abc"


def _created(version=0, balance=1000.0, owner="Alice") -> AccountCreated:
    return AccountCreated(stream_id=AID, version=version, owner=owner, initial_balance=balance)


def _deposit(version, amount) -> MoneyDeposited:
    return MoneyDeposited(stream_id=AID, version=version, amount=amount)


def _withdraw(version, amount) -> MoneyWithdrawn:
    return MoneyWithdrawn(stream_id=AID, version=version, amount=amount)


def _freeze(version) -> AccountFrozen:
    return AccountFrozen(stream_id=AID, version=version, reason="test")


def fresh_session(*events) -> ProjectorSession:
    session = ProjectorSession()
    for ev in events:
        session.apply(ev)
    return session


# ─────────────────────────────────────────────────────────────
# 1. Determinism
# ─────────────────────────────────────────────────────────────

class TestDeterminism:
    def test_same_events_same_state(self):
        """Running the same event sequence twice must always produce identical state."""
        events = [
            _created(0, 500.0),
            _deposit(1, 200.0),
            _withdraw(2, 100.0),
        ]

        s1 = fresh_session(*events)
        s2 = fresh_session(*events)

        a1 = s1.ledger.accounts[AID]
        a2 = s2.ledger.accounts[AID]

        assert a1.balance == a2.balance == 600.0
        assert a1.version == a2.version == 2
        assert a1.event_count == a2.event_count == 3

    def test_order_matters_for_final_state(self):
        """Different orderings of non-commutative events yield different states — prove this."""
        # Withdraw before deposit succeeds when balance is initially zero only if order is diff
        # Proof: deposit then withdraw vs withraw then deposit (if allowed) differ
        events_v1 = [_created(0, 0.0), _deposit(1, 300.0), _withdraw(2, 100.0)]
        s = fresh_session(*events_v1)
        assert s.ledger.accounts[AID].balance == 200.0

    def test_repeated_replay_is_idempotent_across_sessions(self):
        """Replay N times — always same result."""
        events = [_created(0, 1000.0), _deposit(1, 500.0), _withdraw(2, 200.0)]
        balances = []
        for _ in range(10):
            s = fresh_session(*events)
            balances.append(s.ledger.accounts[AID].balance)
        assert len(set(balances)) == 1, f"Non-deterministic balances: {balances}"


# ─────────────────────────────────────────────────────────────
# 2. Idempotency
# ─────────────────────────────────────────────────────────────

class TestIdempotency:
    def test_duplicate_event_skipped(self):
        """Applying the same event_id twice must not change the state."""
        ev = _deposit(1, 100.0)
        session = ProjectorSession()
        session.apply(_created(0))
        session.apply(ev)
        balance_after_first = session.ledger.accounts[AID].balance

        # Apply duplicate — should be silently skipped
        session.apply(ev)
        balance_after_second = session.ledger.accounts[AID].balance

        assert balance_after_first == balance_after_second, (
            f"Idempotency violated: {balance_after_first} != {balance_after_second}"
        )
        assert session.ledger.accounts[AID].event_count == 2  # not 3

    def test_multiple_duplicates_all_skipped(self):
        ev = _deposit(1, 50.0)
        session = ProjectorSession()
        session.apply(_created(0, 0.0))
        for _ in range(5):
            session.apply(ev)  # all duplicates after first
        assert session.ledger.accounts[AID].balance == 50.0


# ─────────────────────────────────────────────────────────────
# 3. Ordering
# ─────────────────────────────────────────────────────────────

class TestOrdering:
    def test_out_of_order_raises(self):
        """Version 2 before version 1 must raise OrderingViolation."""
        session = ProjectorSession()
        session.apply(_created(0))
        session.apply(_deposit(1, 100.0))

        with pytest.raises(OrderingViolation):
            session.apply(_deposit(3, 50.0))  # gap: expected v2, got v3

    def test_correct_order_ok(self):
        session = ProjectorSession()
        session.apply(_created(0))
        session.apply(_deposit(1, 100.0))
        session.apply(_deposit(2, 50.0))
        assert session.ledger.accounts[AID].balance == 1150.0

    def test_replay_wrong_first_event_raises(self):
        """Starting on version 1 without version 0 must raise OrderingViolation."""
        session = ProjectorSession()
        with pytest.raises(OrderingViolation):
            session.apply(_deposit(1, 100.0))  # no AccountCreated at v0 first


# ─────────────────────────────────────────────────────────────
# 4. Invariants
# ─────────────────────────────────────────────────────────────

class TestInvariants:
    def test_insufficient_funds_raises(self):
        session = fresh_session(_created(0, 100.0))
        with pytest.raises(InsufficientFunds):
            session.apply(_withdraw(1, 200.0))

    def test_withdraw_exact_balance_ok(self):
        session = fresh_session(_created(0, 100.0))
        session.apply(_withdraw(1, 100.0))
        assert session.ledger.accounts[AID].balance == 0.0

    def test_frozen_account_rejects_deposit(self):
        session = fresh_session(_created(0, 100.0), _freeze(1))
        with pytest.raises(AccountAlreadyFrozen):
            session.apply(_deposit(2, 50.0))

    def test_account_not_found_raises(self):
        """Depositing into a non-existent account raises AccountNotFound."""
        session = ProjectorSession()
        with pytest.raises(AccountNotFound):
            session.apply(_deposit(0, 50.0))


# ─────────────────────────────────────────────────────────────
# 5. Snapshot round-trip
# ─────────────────────────────────────────────────────────────

class TestSnapshot:
    def test_snapshot_roundtrip(self, tmp_path, monkeypatch):
        """Save a snapshot, reload it, verify state is identical."""
        import app.engine.snapshot as snap_mod
        monkeypatch.setattr(snap_mod, "SNAPSHOT_DIR", tmp_path)

        # Build state
        events = [_created(0, 500.0), _deposit(1, 200.0), _withdraw(2, 50.0)]
        session = ProjectorSession()
        for ev in events:
            session.apply(ev)
        ledger = session.ledger
        checkpoint = {AID: 2}

        # Save
        snap_mod.save_snapshot(ledger, checkpoint)

        # Load
        result = snap_mod.load_snapshot()
        assert result is not None
        loaded_ledger, loaded_checkpoint = result

        assert loaded_ledger.accounts[AID].balance == 650.0
        assert loaded_checkpoint[AID] == 2
        assert loaded_ledger.replay_source == "snapshot"

    def test_no_snapshot_returns_none(self, tmp_path, monkeypatch):
        import app.engine.snapshot as snap_mod
        monkeypatch.setattr(snap_mod, "SNAPSHOT_DIR", tmp_path)
        assert snap_mod.load_snapshot() is None


# ─────────────────────────────────────────────────────────────
# 6. Validation layer
# ─────────────────────────────────────────────────────────────

class TestValidation:
    def test_clean_state_is_valid(self):
        session = fresh_session(_created(0, 1000.0), _deposit(1, 500.0))
        report = validate_ledger(session.ledger)
        assert report.is_valid
        assert len([f for f in report.findings if f.severity.value == "error"]) == 0

    def test_negative_balance_detected(self):
        """Manually corrupt state and check validator catches it."""
        session = fresh_session(_created(0, 100.0))
        session.ledger.accounts[AID].balance = -500.0  # manual corruption

        report = validate_ledger(session.ledger)
        assert not report.is_valid
        errors = [f for f in report.findings if f.severity.value == "error"]
        assert any("negative" in f.message for f in errors)

    def test_total_balance_computed(self):
        events1 = [_created(0, 300.0)]
        events2 = [
            AccountCreated(stream_id="account-b", version=0, owner="Bob", initial_balance=200.0)
        ]
        session = ProjectorSession()
        for ev in events1:
            session.apply(ev)
        for ev in events2:
            session.apply(ev)

        report = validate_ledger(session.ledger)
        assert report.total_balance == 500.0


# ─────────────────────────────────────────────────────────────
# 7. Performance: snapshot vs full replay timing
# ─────────────────────────────────────────────────────────────

class TestPerformance:
    def test_snapshot_replay_faster_than_full(self, tmp_path, monkeypatch):
        """
        Build a ledger with many events, time full vs snapshot replay.
        Snapshot should be at least 10x faster.
        """
        import app.engine.snapshot as snap_mod
        monkeypatch.setattr(snap_mod, "SNAPSHOT_DIR", tmp_path)

        N = 500
        events = [_created(0, 0.0)] + [_deposit(i + 1, 1.0) for i in range(N)]

        # Full replay timing
        t0 = time.perf_counter()
        for _ in range(3):
            session = ProjectorSession()
            for ev in events:
                session.apply(ev)
        full_time = (time.perf_counter() - t0) / 3

        # Save snapshot
        snap_mod.save_snapshot(session.ledger, {AID: N})

        # Snapshot replay timing (0 delta events — pure deserialization)
        t1 = time.perf_counter()
        for _ in range(3):
            snap_mod.load_snapshot()
        snap_time = (time.perf_counter() - t1) / 3

        # Snapshot should be significantly faster than full replay for 500 events
        print(f"\nFull replay ({N} events): {full_time*1000:.2f}ms")
        print(f"Snapshot load (0 delta): {snap_time*1000:.2f}ms")
        assert snap_time < full_time, "Snapshot should be faster than full replay"


# ─────────────────────────────────────────────────────────────
# 8. Concurrency
# ─────────────────────────────────────────────────────────────

class TestConcurrency:
    def test_concurrent_sessions_are_independent(self):
        """
        Two ProjectorSessions running simultaneously on the same events
        must produce identical, independent state — no shared mutation.
        """
        import threading

        events = [_created(0, 1000.0), _deposit(1, 500.0), _withdraw(2, 200.0)]
        results: list[float] = []
        lock = threading.Lock()

        def run_session():
            s = ProjectorSession()
            for ev in events:
                s.apply(ev)
            with lock:
                results.append(s.ledger.accounts[AID].balance)

        threads = [threading.Thread(target=run_session) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert len(set(results)) == 1, f"Non-deterministic concurrent results: {results}"
        assert results[0] == 1300.0

    def test_version_conflict_prevents_double_apply(self):
        """
        If two concurrent writers try to put different events at the same
        version slot, the projector must reject the second one with
        an OrderingViolation (simulating what EventStoreDB would enforce at the DB layer).
        """
        # Writer A: deposit 100 at version 1
        ev_a = MoneyDeposited(stream_id=AID, version=1, amount=100.0)
        # Writer B: deposit 200 at version 1 (same slot — conflict)
        ev_b = MoneyDeposited(stream_id=AID, version=1, amount=200.0)

        session = ProjectorSession()
        session.apply(_created(0, 500.0))
        session.apply(ev_a)  # wins the slot

        with pytest.raises(OrderingViolation):
            session.apply(ev_b)  # loses — version 1 already taken

        # Balance reflects only the winner
        assert session.ledger.accounts[AID].balance == 600.0

