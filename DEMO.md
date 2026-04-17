# RewindDB — Judge Demo Guide

## Context
Every step below is a live HTTP call. Use the Swagger UI at http://localhost:8000/docs.

---

## Step 1: Seed Demo Data (30 seconds)

```http
POST /simulate/seed
{
  "num_accounts": 3,
  "transactions_per_account": 4
}
```

Expected output: 3 accounts created, deposits applied, cross-account transfer done.

---

## Step 2: View the Event Log (Prove the append-only log)

```http
GET /queries/streams
```
→ Lists all `account-demo-*` streams.

```http
GET /queries/events/{account_id}
```
→ Shows the raw, immutable event log in sequence order.

**Judge point:** Every entry has `event_id`, `version`, `occurred_at` — the full audit trail.

---

## Step 3: Build State from Events

```http
GET /queries/state
```
→ Triggers a full replay. Response includes:
- Current balances
- `replay_source: "full"`
- `duration_ms` — how long replay took

**Judge point:** State is NOT stored. It is rebuilt fresh every time from the event log.

---

## Step 4: Simulate a CRASH

```http
POST /simulate/crash
```
→ Deletes the in-memory snapshot. The system has "forgotten" everything.

Now call state again:
```http
GET /queries/replay?mode=full
```
→ System rebuilds identical state from EventStoreDB. Compare balances — they match.

**Judge point:** After crash, replay produces **byte-identical** output. Determinism proven.

---

## Step 5: Prove IDEMPOTENCY

```http
POST /simulate/duplicate
{
  "account_id": "{any_account_id}",
  "amount": 100.0
}
```

Expected response:
```json
{
  "recovered": true,
  "system_response": "Idempotency guard blocked duplicate — balance unchanged"
}
```

**Judge point:** Sending the same money event 5 times does not change the balance.

---

## Step 6: Prove ORDERING GUARANTEES

```http
POST /simulate/out-of-order
{
  "account_id": "{any_account_id}"
}
```

Expected response:
```json
{
  "recovered": true,
  "system_response": "OrderingViolation raised: Stream account-...: expected version 0, got 1..."
}
```

**Judge point:** Swapped events are immediately rejected. The projector never applies events in wrong order.

---

## Step 7: Prove STATE RECOVERY after CORRUPTION

```http
POST /simulate/corruption
{
  "account_id": "{any_account_id}"
}
```

Expected response:
```json
{
  "scenario": "state_corruption",
  "injected": "Corrupted balance: 1650.00 → 11649.99",
  "system_response": "Replay recovered correct balance: 1650.00",
  "recovered": true
}
```

**Judge point:** You can corrupt memory all you want. The event log is the source of truth. Replay always wins.

---

## Step 8: Snapshot Performance

```http
GET /queries/replay?mode=full
```
Note the `duration_ms`.

```http
POST /simulate/crash
GET /queries/replay?mode=snapshot
```
Note the `duration_ms` — it should be significantly lower.

**Judge point:** Snapshot replay is faster because we skip already-processed events. Both produce identical state.

---

## Step 9: Validation Layer

```http
GET /queries/validate
```

Expected:
```json
{
  "validation": {
    "is_valid": true,
    "findings": []
  }
}
```

**Judge point:** Post-replay validation confirms no invariants are broken (no negative balances, no orphaned state).

---

## Step 10: Time Travel (Bonus)

```http
GET /queries/replay?mode=full&until=2025-01-01T00:00:00
```

→ Rebuild state as it was at `2025-01-01`. Any events after that timestamp are ignored.

**Judge point:** Because events carry timestamps, we can replay to any point in history.

---

## Failure Scenarios Summary

| Scenario | Injected | System Response | Recovered |
|---|---|---|---|
| Crash | Snapshot deleted | Full replay from EventStoreDB | ✅ |
| Duplicate event | Same event_id applied 2x | Idempotency guard skips it | ✅ |
| Out-of-order | Events swapped | OrderingViolation raised | ✅ |
| Missing event | Version gap created | OrderingViolation raised | ✅ |
| State corruption | Balance set to garbage | Replay restores correct value | ✅ |
