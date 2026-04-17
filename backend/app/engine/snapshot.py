"""
Snapshot System

Problem: replaying 10 000 events to rebuild state is slow.
Solution: periodically serialize the current LedgerState to a file-based
          snapshot store, tagged with the last applied event version per stream.

On replay:
  1. Load latest snapshot (O(1) deserialization)
  2. Read only events AFTER the snapshot checkpoint from EventStoreDB
  3. Apply the delta normally via ProjectorSession

This proves "Snapshot ≡ shortcut through the event log" — the final state is
identical whether you start from scratch or from a snapshot.

Storage: local JSON files in data/snapshots/.
(In prod you'd use S3/blob storage, but for a hackathon local FS is fine and
 avoids external dependencies.)
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from app.domain.models import AccountState, AccountStatus, LedgerState

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path(os.getenv("SNAPSHOT_DIR", "data/snapshots"))
SNAPSHOT_INTERVAL = int(os.getenv("SNAPSHOT_INTERVAL", "5"))  # events


def _ensure_dir() -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def _snapshot_path() -> Path:
    return SNAPSHOT_DIR / "ledger_snapshot.json"


# ─────────────────────────────────────────────────────────────
# Save
# ─────────────────────────────────────────────────────────────

def save_snapshot(ledger: LedgerState, checkpoint: dict[str, int]) -> None:
    """
    Serialize LedgerState + per-stream version checkpoints to a JSON file.

    `checkpoint` = { stream_id: last_applied_version }
    This is what the replay engine uses to resume from the right position.
    """
    _ensure_dir()
    payload = {
        "accounts": {
            aid: {
                "account_id": acc.account_id,
                "owner": acc.owner,
                "balance": acc.balance,
                "status": acc.status.value,
                "version": acc.version,
                "event_count": acc.event_count,
                "created_at": acc.created_at.isoformat() if acc.created_at else None,
                "last_updated": acc.last_updated.isoformat() if acc.last_updated else None,
            }
            for aid, acc in ledger.accounts.items()
        },
        "total_events_processed": ledger.total_events_processed,
        "checkpoint": checkpoint,
        "saved_at": time.time(),
    }
    path = _snapshot_path()
    path.write_text(json.dumps(payload, indent=2))
    logger.info("Snapshot saved → %s (checkpoint=%s)", path, checkpoint)


# ─────────────────────────────────────────────────────────────
# Load
# ─────────────────────────────────────────────────────────────

def load_snapshot() -> tuple[LedgerState, dict[str, int]] | None:
    """
    Load the latest snapshot.

    Returns (LedgerState, checkpoint_dict) or None if no snapshot exists.
    """
    from datetime import datetime, timezone

    path = _snapshot_path()
    if not path.exists():
        return None

    raw = json.loads(path.read_text())

    ledger = LedgerState(replay_source="snapshot")
    ledger.total_events_processed = raw.get("total_events_processed", 0)

    for aid, data in raw["accounts"].items():
        created_at = (
            datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None
        )
        last_updated = (
            datetime.fromisoformat(data["last_updated"]) if data.get("last_updated") else None
        )
        acc = AccountState(
            account_id=data["account_id"],
            owner=data["owner"],
            balance=data["balance"],
            status=AccountStatus(data["status"]),
            version=data["version"],
            event_count=data["event_count"],
            created_at=created_at,
            last_updated=last_updated,
        )
        ledger.accounts[aid] = acc

    checkpoint: dict[str, int] = raw.get("checkpoint", {})
    logger.info("Snapshot loaded ← %s (checkpoint=%s)", path, checkpoint)
    return ledger, checkpoint


def delete_snapshot() -> None:
    path = _snapshot_path()
    if path.exists():
        path.unlink()
        logger.info("Snapshot deleted")
