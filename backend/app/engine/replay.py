"""
Replay Engine — orchestrates full and snapshot-assisted replays.

This is what runs after a "crash" to rebuild state from the event log.

Two modes:
  1. FULL REPLAY   — read every event from position 0 on every stream
  2. SNAPSHOT REPLAY — load snapshot, then read only delta events

The engine also:
  - emits replay metrics (time, event count, source)
  - handles mid-replay failures gracefully (returns partial state + error)
  - supports "time travel" (replay up to a given UTC timestamp)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.events import BaseEvent
from app.domain.models import LedgerState
from app.engine import event_store as es
from app.engine.projector import (
    OrderingViolation,
    ProjectorSession,
    UnknownEventType,
)
from app.engine.snapshot import load_snapshot, save_snapshot

logger = logging.getLogger(__name__)

STREAM_PREFIX = "account-"


# ─────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────

@dataclass
class ReplayMetrics:
    mode: str           # "full" | "snapshot"
    duration_ms: float
    events_processed: int
    streams_processed: int
    errors: list[str] = field(default_factory=list)
    success: bool = True

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "duration_ms": round(self.duration_ms, 3),
            "events_processed": self.events_processed,
            "streams_processed": self.streams_processed,
            "errors": self.errors,
            "success": self.success,
        }


# ─────────────────────────────────────────────────────────────
# Engine
# ─────────────────────────────────────────────────────────────

def replay_full(
    until: datetime | None = None,
    save_snap: bool = True,
) -> tuple[LedgerState, ReplayMetrics]:
    """
    Full replay from position 0 across all account streams.

    Parameters
    ----------
    until : datetime | None
        If set, stop applying events whose `occurred_at` > until.
        This implements "time travel" — rebuild state as of a past moment.
    save_snap : bool
        If True, save a snapshot after successful replay.
    """
    start = time.perf_counter()

    streams = _discover_streams()
    session = ProjectorSession()
    errors: list[str] = []

    for stream_id in streams:
        _replay_stream(session, stream_id, from_version=0, until=until, errors=errors)

    ledger = session.ledger
    ledger.replay_source = "full"

    elapsed_ms = (time.perf_counter() - start) * 1000

    metrics = ReplayMetrics(
        mode="full",
        duration_ms=elapsed_ms,
        events_processed=ledger.total_events_processed,
        streams_processed=len(streams),
        errors=errors,
        success=len(errors) == 0,
    )
    logger.info("Full replay complete: %s", metrics)

    if save_snap and metrics.success:
        checkpoint = {s: session.ledger.accounts[s].version for s in ledger.accounts}
        save_snapshot(ledger, checkpoint)

    return ledger, metrics


def replay_from_snapshot(
    until: datetime | None = None,
) -> tuple[LedgerState, ReplayMetrics]:
    """
    Snapshot-assisted replay.

    Tries to load a snapshot first. If none exists, falls back to full replay.
    Then applies only events after the snapshot checkpoint.
    """
    start = time.perf_counter()

    snap = load_snapshot()
    if snap is None:
        logger.info("No snapshot found — falling back to full replay")
        ledger, metrics = replay_full(until=until, save_snap=True)
        metrics.mode = "snapshot_fallback"
        return ledger, metrics

    ledger, checkpoint = snap

    # Re-hydrate a projector session from the snapshot state
    session = _session_from_ledger(ledger, checkpoint)

    streams = _discover_streams()
    errors: list[str] = []

    for stream_id in streams:
        # resume from the version AFTER the snapshot checkpoint
        resume_from = checkpoint.get(stream_id, -1) + 1
        _replay_stream(session, stream_id, from_version=resume_from, until=until, errors=errors)

    result_ledger = session.ledger
    result_ledger.replay_source = "snapshot"

    elapsed_ms = (time.perf_counter() - start) * 1000

    metrics = ReplayMetrics(
        mode="snapshot",
        duration_ms=elapsed_ms,
        events_processed=result_ledger.total_events_processed,
        streams_processed=len(streams),
        errors=errors,
        success=len(errors) == 0,
    )
    logger.info("Snapshot replay complete: %s", metrics)
    return result_ledger, metrics


# ─────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────

def _discover_streams() -> list[str]:
    """Return all account stream IDs by listing EventStoreDB $streams."""
    streams = es.list_streams_with_prefix(STREAM_PREFIX)
    logger.info("Discovered %d streams: %s", len(streams), streams)
    return streams


def _replay_stream(
    session: ProjectorSession,
    stream_id: str,
    from_version: int,
    until: datetime | None,
    errors: list[str],
) -> None:
    """Apply events from a single stream into the session, collecting errors."""
    for event in es.read_stream(stream_id, from_version=from_version):
        if until is not None and event.occurred_at > until:
            break
        try:
            session.apply(event)
        except OrderingViolation as exc:
            msg = f"[{stream_id}] Ordering violation: {exc}"
            logger.error(msg)
            errors.append(msg)
            break  # stop processing this stream on ordering violation
        except UnknownEventType as exc:
            msg = f"[{stream_id}] Unknown event type: {exc}"
            logger.warning(msg)
            errors.append(msg)
        except Exception as exc:
            msg = f"[{stream_id}] Apply error on event {getattr(event, 'event_id', '?')}: {exc}"
            logger.error(msg)
            errors.append(msg)


def _session_from_ledger(ledger: LedgerState, checkpoint: dict[str, int]) -> ProjectorSession:
    """
    Boot a ProjectorSession pre-populated with snapshot state.

    We manually set internal tracking so the session resumes ordering checks
    from the correct version (not from -1).
    """
    session = ProjectorSession(ledger=ledger)
    # pre-seed version tracker so ordering guard knows the current version
    for stream_id, version in checkpoint.items():
        session._stream_versions[stream_id] = version  # noqa: SLF001
    return session
