"""
EventStore Client — thin wrapper around esdbclient.

Responsibilities:
  - append events to a named stream (with optimistic concurrency check)
  - read all events from a stream (for replay / projection)
  - read events after a given position (for incremental replay from snapshot)

EventStoreDB connection string comes from the env-var ESDB_CONNECTION_STRING.
Default: esdb://localhost:2113?tls=false
"""

from __future__ import annotations

import json
import logging
import os
from typing import Iterator
from uuid import UUID, uuid4

from esdbclient import EventStoreDBClient, NewEvent, RecordedEvent, StreamState

from app.domain.events import EVENT_MAP, BaseEvent

logger = logging.getLogger(__name__)

ESDB_URL = os.getenv("ESDB_CONNECTION_STRING", "esdb://localhost:2113?tls=false")


def _get_client() -> EventStoreDBClient:
    return EventStoreDBClient(uri=ESDB_URL)


# ─────────────────────────────────────────────────────────────
# Write
# ─────────────────────────────────────────────────────────────

def append_event(event: BaseEvent, stream_id: str | None = None) -> None:
    """
    Append a single domain event to EventStoreDB.

    Uses optimistic concurrency: if `event.version == 0` we expect NO existing
    stream (StreamState.NO_STREAM).  Otherwise we expect exactly
    `event.version - 1` as the last position.

    This prevents phantom writes and ensures strict ordering.
    """
    sid = stream_id or event.stream_id
    client = _get_client()

    raw = NewEvent(
        id=UUID(event.event_id),
        type=event.type,  # type: ignore[attr-defined]
        data=event.model_dump_json().encode(),
    )

    # Optimistic concurrency via expected version
    if event.version == 0:
        expected = StreamState.NO_STREAM
    else:
        expected = event.version - 1  # EventStoreDB uses 0-based position

    try:
        client.append_to_stream(sid, current_version=expected, events=[raw])
        logger.info("Appended %s v%d → %s", event.type, event.version, sid)  # type: ignore[attr-defined]
    except Exception as exc:
        logger.error("Failed to append to %s: %s", sid, exc)
        raise


def append_events(events: list[BaseEvent], stream_id: str | None = None) -> None:
    """Append multiple events atomically to the same stream."""
    if not events:
        return
    sid = stream_id or events[0].stream_id
    client = _get_client()

    raw_events = [
        NewEvent(
            id=UUID(e.event_id),
            type=e.type,  # type: ignore[attr-defined]
            data=e.model_dump_json().encode(),
        )
        for e in events
    ]

    first_version = events[0].version
    expected = StreamState.NO_STREAM if first_version == 0 else first_version - 1

    client.append_to_stream(sid, current_version=expected, events=raw_events)
    logger.info("Batch-appended %d events → %s", len(events), sid)


# ─────────────────────────────────────────────────────────────
# Read
# ─────────────────────────────────────────────────────────────

def read_stream(stream_id: str, from_version: int = 0) -> Iterator[BaseEvent]:
    """
    Yields deserialized domain events from a stream in strict sequence order.

    `from_version` lets you resume from a snapshot checkpoint — we skip
    events before that version for efficiency.
    """
    client = _get_client()
    try:
        recorded: Iterator[RecordedEvent] = client.read_stream(
            stream_id,
            stream_position=from_version,
        )
        for rec in recorded:
            event_type = rec.type
            cls = EVENT_MAP.get(event_type)
            if cls is None:
                logger.warning("Unknown event type: %s — skipping", event_type)
                continue
            payload = json.loads(rec.data.decode())
            yield cls(**payload)
    except Exception as exc:
        # Stream not found means no events yet — not an error
        if "not found" in str(exc).lower() or "stream deleted" in str(exc).lower():
            return
        raise


def list_streams_with_prefix(prefix: str) -> list[str]:
    """
    Return all stream IDs that start with a given prefix.

    EventStoreDB $streams projection data format: "position@stream_id"
    e.g. b"0@account-demo-362af2"
    """
    client = _get_client()
    stream_ids: list[str] = []

    try:
        for rec in client.read_stream("$streams"):
            raw = rec.data.decode().strip()
            # Format: "0@stream_id" — take everything after the first "@"
            if "@" in raw:
                sid = raw.split("@", 1)[1]
            else:
                sid = raw
            if sid.startswith(prefix) and sid not in stream_ids:
                stream_ids.append(sid)
    except Exception as exc:
        logger.warning("Failed to read $streams: %s", exc)

    return stream_ids
