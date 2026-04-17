# RewindDB

> **"State is a pure function of events."**

A competition-grade event-sourced state recovery system built on EventStoreDB.
Proving mathematically and practically that *correct state can always be reconstructed using only the append-only event log.*

---

## Problem Statement

> Design a System That Can Recover Correct State After Failure Using Only Logged Events

**Domain:** Financial Ledger (Accounts, Deposits, Withdrawals, Transfers)

Judges can instantly verify correctness: if a transfer executes twice (idempotency failure), a balance drops double. If events arrive out of order, an account may incorrectly go negative. RewindDB prevents all of this.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     CLIENT / FRONTEND                   │
└─────────────────────┬───────────────────────────────────┘
                      │ HTTP
┌─────────────────────▼───────────────────────────────────┐
│                  FastAPI Backend                        │
│  ┌──────────┐  ┌──────────┐  ┌─────────────────────┐   │
│  │ Commands │  │ Queries  │  │  Simulation API      │   │
│  │ (writes) │  │ (reads)  │  │ (crash/dup/ordering) │   │
│  └────┬─────┘  └────┬─────┘  └──────────┬──────────┘   │
│       │              │                   │              │
│  ┌────▼──────────────▼───────────────────▼──────────┐   │
│  │              Replay Engine                        │   │
│  │  ┌─────────────┐  ┌────────────┐  ┌───────────┐  │   │
│  │  │  Projector  │  │  Snapshot  │  │ Validator │  │   │
│  │  │  Session    │  │  System    │  │  Layer    │  │   │
│  │  └─────────────┘  └────────────┘  └───────────┘  │   │
│  └───────────────────────┬───────────────────────────┘   │
│                          │                               │
│  ┌───────────────────────▼───────────────────────────┐   │
│  │             EventStoreDB Client                   │   │
│  └───────────────────────┬───────────────────────────┘   │
└──────────────────────────┼──────────────────────────────┘
                           │ gRPC
┌──────────────────────────▼──────────────────────────────┐
│              EventStoreDB (Docker)                      │
│         Append-Only Stream Storage                      │
└─────────────────────────────────────────────────────────┘
```

---

## Core Properties Proven

| Property | Mechanism | Test |
|---|---|---|
| **Determinism** | No side-effects in handlers; time from event only | `TestDeterminism` — 10x replays, identical state |
| **Idempotency** | `event_id` set per session; duplicates silently skipped | `TestIdempotency` — balance unchanged after 5x same event |
| **Ordering** | Strict version counter; gap/swap → `OrderingViolation` | `TestOrdering` — out-of-order raises immediately |
| **Snapshots** | JSON checkpoint + delta replay | `TestSnapshot` — round-trip produces same balance |
| **Validation** | Post-replay invariant checks | `TestValidation` — catches negative balances |

---

## API Endpoints

### Commands (Write)
| Method | Path | Description |
|---|---|---|
| POST | `/commands/accounts` | Create account |
| POST | `/commands/accounts/{id}/deposit` | Deposit funds |
| POST | `/commands/accounts/{id}/withdraw` | Withdraw funds |
| POST | `/commands/accounts/{id}/transfer` | Transfer between accounts |
| POST | `/commands/accounts/{id}/freeze` | Freeze account |

### Queries (Read)
| Method | Path | Description |
|---|---|---|
| GET | `/queries/state` | Full ledger (triggers replay) |
| GET | `/queries/state/{id}` | Single account state |
| GET | `/queries/events/{id}` | Raw event log |
| GET | `/queries/replay?mode=full\|snapshot` | Replay + metrics |
| GET | `/queries/validate` | Run validation layer |
| GET | `/queries/streams` | List all streams |

### Simulation (Chaos)
| Method | Path | Description |
|---|---|---|
| POST | `/simulate/crash` | Wipe snapshot (forces full replay) |
| POST | `/simulate/duplicate` | Inject duplicate event |
| POST | `/simulate/out-of-order` | Swap events, prove ordering guard |
| POST | `/simulate/missing` | Skip event, prove gap detection |
| POST | `/simulate/corruption` | Corrupt state, prove replay restores |
| POST | `/simulate/seed` | Seed demo data |
| DELETE | `/simulate/reset` | Clear snapshots |

---

## Design Decisions & Tradeoffs

### Why Event Sourcing?
- State is **derived**, not stored — no `UPDATE` statements possible
- Full audit trail by default
- Time-travel queries are trivial (`?until=2025-01-01T00:00:00`)
- Failure recovery = replay, not backup restore

### Why Not a Traditional DB?
- Traditional DBs store *current* state — crash recovery requires WAL + checkpoints implemented by DB internals (hidden from you)
- We **expose** and **prove** the recovery mechanism explicitly

### Why EventStoreDB over Kafka?
- Kafka is a message broker — streams are consumed and deleted
- EventStoreDB is a **permanent, indexed event store** — streams stay forever, replay is O(1) seek
- Native optimistic concurrency (expected version) prevents concurrent write conflicts

### Limitations
- No multi-stream atomic transactions (two-phase commit needed for transfer atomicity in production)
- Snapshot store is local filesystem (would use object storage in prod)
- No subscription-based live projections (would use EventStoreDB persistent subscriptions in prod)

---

## Setup

### Prerequisites
- Python 3.9+
- Docker Desktop

### Start

```bash
# Open Docker Desktop first, then:
./start.sh
```

This will:
1. Launch EventStoreDB on port 2113
2. Install Python dependencies
3. Start FastAPI on port 8000

### API Docs
- Swagger UI: http://localhost:8000/docs
- EventStoreDB UI: http://localhost:2113

### Run Tests (no Docker needed)
```bash
cd backend
source .venv/bin/activate
pytest -v
```

---

## Demo Flow

See [`DEMO.md`](DEMO.md) for the step-by-step judge demonstration.
