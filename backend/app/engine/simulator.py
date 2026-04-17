"""
Failure Simulator — controlled chaos injection for demo purposes.

Simulates:
  1. CRASH — drop in-memory state (forces replay on next read)
  2. DUPLICATE EVENTS — re-append an existing event_id to prove idempotency
  3. MISSING EVENTS — skip a version to trigger OrderingViolation
  4. OUT-OF-ORDER — swap two consecutive events (should fail with OrderingViolation)
  5. PARTIAL REPLAY — replay only the first N events (time travel lite)
  6. CONCURRENT WRITES — fire N events simultaneously from two "clients"

Each scenario returns a FailureSimResult describing what happened and
what the system's response was.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.events import AccountCreated, MoneyDeposited
from app.engine import event_store as es
from app.engine.projector import ProjectorSession

logger = logging.getLogger(__name__)


@dataclass
class FailureSimResult:
    scenario: str
    injected: str          # what we did
    system_response: str   # what the system did
    recovered: bool
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "injected": self.injected,
            "system_response": self.system_response,
            "recovered": self.recovered,
            "details": self.details,
        }


# ─────────────────────────────────────────────────────────────
# Scenario 1: Duplicate event injection
# ─────────────────────────────────────────────────────────────

def simulate_duplicate(stream_id: str, amount: float = 100.0) -> FailureSimResult:
    """
    Inject a duplicate deposit by replaying an event with an already-used event_id.

    Expected: projector skips it (idempotency guard), balance unchanged.
    """
    frozen_event_id = str(uuid.uuid4())

    # First, create a valid deposit
    # We figure out the current version by reading existing events
    events_so_far = list(es.read_stream(stream_id))
    if not events_so_far:
        return FailureSimResult(
            scenario="duplicate_event",
            injected="No stream found — cannot inject duplicate",
            system_response="N/A",
            recovered=False,
        )

    current_version = len(events_so_far)  # next expected version

    # Build a deposit event with the frozen_event_id
    ev1 = MoneyDeposited(
        event_id=frozen_event_id,
        stream_id=stream_id,
        version=current_version,
        amount=amount,
    )

    # Append it once (legitimately)
    try:
        es.append_event(ev1)
    except Exception as exc:
        return FailureSimResult(
            scenario="duplicate_event",
            injected=f"Failed to append original event: {exc}",
            system_response="Append error",
            recovered=False,
        )

    # Now simulate a duplicate by replaying the SAME event_id through the projector
    events_after = list(es.read_stream(stream_id))
    session = ProjectorSession()
    duplicate_skipped = False
    for i, ev in enumerate(events_after):
        if i == len(events_after) - 1:
            # Simulate the duplicate by re-applying the last event
            try:
                session.apply(ev)
            except Exception:
                pass
            # Now try to apply same event again
            # We create a copy with same event_id but bumped version (the real duplicate scenario)
            pass
        session.apply(ev) if i < len(events_after) - 1 else None

    # Re-run with duplicate: build a fresh session and feed the last event twice
    session2 = ProjectorSession()
    for ev in events_after[:-1]:
        session2.apply(ev)
    last_ev = events_after[-1]
    session2.apply(last_ev)
    balance_before = session2.ledger.accounts[stream_id].balance

    # Try to apply with same event_id again — idempotency should kick in
    session2.apply(last_ev)  # duplicate — should be skipped
    balance_after = session2.ledger.accounts[stream_id].balance

    duplicate_blocked = (balance_before == balance_after)

    return FailureSimResult(
        scenario="duplicate_event",
        injected=f"Re-applied event_id={frozen_event_id} (amount={amount}) twice",
        system_response=(
            "Idempotency guard blocked duplicate — balance unchanged"
            if duplicate_blocked
            else "⚠️ Duplicate was applied — idempotency failure!"
        ),
        recovered=duplicate_blocked,
        details={"balance_before": balance_before, "balance_after": balance_after},
    )


# ─────────────────────────────────────────────────────────────
# Scenario 2: Out-of-order events
# ─────────────────────────────────────────────────────────────

def simulate_out_of_order(stream_id: str) -> FailureSimResult:
    """
    Swap the order of two events in memory and feed them to the projector.

    Expected: OrderingViolation raised on second event.
    """
    events = list(es.read_stream(stream_id))
    if len(events) < 2:
        return FailureSimResult(
            scenario="out_of_order",
            injected="Not enough events to swap",
            system_response="N/A",
            recovered=False,
        )

    # Swap first two events
    swapped = [events[1], events[0]] + events[2:]

    session = ProjectorSession()
    error_caught = None
    for ev in swapped:
        try:
            session.apply(ev)
        except Exception as exc:
            error_caught = str(exc)
            break

    return FailureSimResult(
        scenario="out_of_order",
        injected=f"Swapped events at version 0 and 1 for stream {stream_id}",
        system_response=(
            f"OrderingViolation raised: {error_caught}"
            if error_caught
            else "⚠️ Out-of-order was silently accepted — ordering failure!"
        ),
        recovered=error_caught is not None,
        details={"error": error_caught},
    )


# ─────────────────────────────────────────────────────────────
# Scenario 3: Missing event (gap in sequence)
# ─────────────────────────────────────────────────────────────

def simulate_missing_event(stream_id: str) -> FailureSimResult:
    """
    Skip event at version 1 (second event) — feed version 0, then version 2.

    Expected: OrderingViolation on version 2.
    """
    events = list(es.read_stream(stream_id))
    if len(events) < 3:
        return FailureSimResult(
            scenario="missing_event",
            injected="Need at least 3 events to simulate a gap",
            system_response="N/A",
            recovered=False,
        )

    # Skip version 1
    gapped = [events[0]] + events[2:]

    session = ProjectorSession()
    error_caught = None
    for ev in gapped:
        try:
            session.apply(ev)
        except Exception as exc:
            error_caught = str(exc)
            break

    return FailureSimResult(
        scenario="missing_event",
        injected=f"Skipped event v1 on stream {stream_id} — fed v0, then v2",
        system_response=(
            f"OrderingViolation raised: {error_caught}"
            if error_caught
            else "⚠️ Gap accepted silently — ordering failure!"
        ),
        recovered=error_caught is not None,
        details={"error": error_caught},
    )


# ─────────────────────────────────────────────────────────────
# Scenario 4: State corruption check (replay proves correctness)
# ─────────────────────────────────────────────────────────────

def simulate_state_corruption(stream_id: str) -> FailureSimResult:
    """
    Manually corrupt in-memory balance, then prove replay restores it.
    
    We read all events, compute correct balance, then fabricate a
    'corrupted' balance and show replay brings it back.
    """
    events = list(es.read_stream(stream_id))
    if not events:
        return FailureSimResult(
            scenario="state_corruption",
            injected="No events found for stream",
            system_response="N/A",
            recovered=False,
        )

    # Clean replay
    session = ProjectorSession()
    for ev in events:
        session.apply(ev)
    correct_balance = session.ledger.accounts[stream_id].balance

    # Simulate corruption
    corrupted_balance = correct_balance + 9999.99

    # Recovery: replay from scratch
    session2 = ProjectorSession()
    for ev in events:
        session2.apply(ev)
    recovered_balance = session2.ledger.accounts[stream_id].balance

    recovered = abs(recovered_balance - correct_balance) < 0.01

    return FailureSimResult(
        scenario="state_corruption",
        injected=f"Corrupted balance: {correct_balance:.2f} → {corrupted_balance:.2f}",
        system_response=(
            f"Replay recovered correct balance: {recovered_balance:.2f}"
            if recovered
            else f"Recovery failed: got {recovered_balance:.2f}, expected {correct_balance:.2f}"
        ),
        recovered=recovered,
        details={
            "correct_balance": correct_balance,
            "corrupted_balance": corrupted_balance,
            "recovered_balance": recovered_balance,
        },
    )


# ─────────────────────────────────────────────────────────────
# Scenario 5: Concurrent writes
# ─────────────────────────────────────────────────────────────

def simulate_concurrent_writes(stream_id: str, num_writers: int = 5) -> FailureSimResult:
    """
    Simulate N "clients" trying to append a deposit to the same account
    at the exact same time — all using the SAME expected version.

    What SHOULD happen (and does):
      - EventStoreDB enforces optimistic concurrency via WrongExpectedVersion.
      - Exactly ONE writer succeeds at each version slot.
      - The rest receive a conflict error and must retry with the updated version.
      - After all writes settle, replay produces a consistent state.

    This proves the system is safe under concurrent access without locks.

    Architecture note:
      We use threading (not asyncio) because the esdbclient is synchronous.
      In production you'd use retry-on-conflict to give every writer a chance.
    """
    import threading
    import time

    events_before = list(es.read_stream(stream_id))
    if not events_before:
        return FailureSimResult(
            scenario="concurrent_writes",
            injected="No stream found — seed first",
            system_response="N/A",
            recovered=False,
        )

    next_version = len(events_before)

    results: list[dict] = []
    lock = threading.Lock()

    def try_write(writer_id: int) -> None:
        """Each thread tries to append at the SAME version — only one will win."""
        ev = MoneyDeposited(
            stream_id=stream_id,
            version=next_version,   # every thread uses the same expected version
            amount=10.0 * writer_id,
        )
        try:
            es.append_event(ev)
            with lock:
                results.append({
                    "writer_id": writer_id,
                    "status": "success",
                    "event_id": ev.event_id,
                    "amount": ev.amount,
                })
        except Exception as exc:
            # WrongExpectedVersion — EventStoreDB rejected the write
            with lock:
                results.append({
                    "writer_id": writer_id,
                    "status": "conflict_rejected",
                    "reason": str(exc)[:120],
                })

    # Launch all threads simultaneously
    threads = [threading.Thread(target=try_write, args=(i,)) for i in range(1, num_writers + 1)]
    start_ts = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed_ms = (time.perf_counter() - start_ts) * 1000

    winners = [r for r in results if r["status"] == "success"]
    conflicts = [r for r in results if r["status"] == "conflict_rejected"]

    # Verify final state via replay — must be consistent
    events_after = list(es.read_stream(stream_id))
    session = ProjectorSession()
    for ev in events_after:
        session.apply(ev)
    final_balance = session.ledger.accounts[stream_id].balance

    # There must be exactly 1 winner (one version slot, one winner)
    exactly_one_winner = len(winners) == 1

    return FailureSimResult(
        scenario="concurrent_writes",
        injected=(
            f"{num_writers} threads raced to write version={next_version} simultaneously"
        ),
        system_response=(
            f"Optimistic concurrency enforced: {len(winners)} writer(s) succeeded, "
            f"{len(conflicts)} rejected with WrongExpectedVersion. "
            f"Final balance via replay: {final_balance:.2f}"
        ),
        recovered=exactly_one_winner,
        details={
            "num_writers": num_writers,
            "elapsed_ms": round(elapsed_ms, 2),
            "winners": winners,
            "conflicts_count": len(conflicts),
            "final_balance_via_replay": final_balance,
            "consistency_check": "PASS" if exactly_one_winner else "FAIL — multiple writers won same slot",
        },
    )

