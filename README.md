<div align="center">
  <img src="https://img.shields.io/badge/Status-Hackathon_Complete-success?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Architecture-Event_Sourcing-blue?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Frontend-Vanilla_JS-f7df1e?style=for-the-badge&logo=javascript&logoColor=black" />
  
  <h1>RewindDB</h1>
  <p><b>"State is a pure function of events."</b></p>
  <p>A competition-grade, zero-dependency event-sourced state recovery system. Built for the Zero-to-One Hackathon.</p>

  <h3><a href="https://rewind-db.vercel.app/?v=2">🔴 Try the Live Demo</a></h3>
</div>

<br />

## 📖 The Philosophy

Traditional databases store the **current state** (e.g., `balance = 500`). When systems crash, reconstructing exactly how you arrived at that state—and proving its correctness—is nearly impossible without digging through internal write-ahead logs.

**RewindDB flips this paradigm.** 
We do not store state. We only store **immutable events** (e.g., `AccountCreated`, `MoneyDeposited`, `MoneyWithdrawn`). The application state is built *on-demand* by projecting the mathematical fold of these history logs. 

If the system crashes, we lose nothing. We simply replay the events.

---

## ⚡ Core Properties Proven

Judges can instantly verify correctness via the built-in **Failure Lab** on the frontend UI:

| Architectural Property | What It Proves | How We Prove It |
|---|---|---|
| **Determinism** | State is derived strictly from events. | Identical starting events *always* produce the exact same final balances across arbitrary thread sizes. |
| **Idempotency** | Duplicate events never corrupt data. | Injecting the exact same `DepositEvent` multiple times is silently ignored and the balance remains accurate. |
| **Ordering Guard** | Processing events out-of-order is rejected. | Built-in version incrementing raises `OrderingViolation` if events are skipped or swapped. |
| **Optimistic Concurrency** | Race conditions cannot overwrite data. | Multi-threaded simulation forces `WrongExpectedVersion` at the database level when threads race. |
| **Rapid Recovery** | System instantly rebuilds state. | Checkpoint snapshots are automatically generated to instantly restore state up to a point without a full N-event replay. |

---

## 🏗 System Architecture

RewindDB is composed of an interactive SPA frontend, a FastAPI event-processing engine, and EventStoreDB acting as our immutable source of truth.

```mermaid
graph TD
    UI[Frontend Dashboard] -->|REST API| API[FastAPI Backend Engine]
    
    subgraph Engine [RewindDB Backend]
        API --> Projector[State Projector]
        API --> Validator[Invariant Validator]
        API --> Sim[Chaos Simulator]
    end
    
    Projector -->|Read / Append / Snapshot| ESDB[(EventStoreDB)]
```

---

## 🚀 Live Demonstration (Vercel + Tunnel)

During the hackathon presentation, we run a hybrid local-cloud architecture:
*   The **Frontend Dashboard** is continuously deployed on Vercel.
*   The **Backend Engine** runs securely on a local machine to eliminate latency during chaos tests.
*   They are connected securely via a **Pinggy** HTTPS tunnel.

### How to Run Locally for Judges:

1. **Start the Engine & Database**
   Make sure Docker Desktop is open, then open a terminal in the project root:
   ```bash
   chmod +x start.sh
   ./start.sh
   ```
   *This starts EventStoreDB on port `2113` and FastAPI on port `8001`.*

2. **Expose the Engine via Pinggy**
   In a new terminal window, start a reverse tunnel to securely expose your backend to Vercel:
   ```bash
   ssh -p 443 -R0:localhost:8001 a.pinggy.io
   ```

3. **Connect the Vercel App**
   - Open your deployed frontend: `https://rewind-db.vercel.app` *(Recommendation: Use an Incognito Window to ensure you bypass caching).*
   - Click the **Gear ⚙️ Icon** to open the Settings modal.
   - Paste the `https://....run.pinggy-free.link` URL provided by the terminal command above.
   - Click **Save & Reconnect**. The offline dot will turn Green.

---

## 🧪 Simulation API (The "Failure Lab")

To prove the core philosophy, we built intentional failure mechanisms accessible via the frontend or API directly:

| Chaos API Endpoint | Description |
|---|---|
| `POST /simulate/duplicate` | Attempts to insert an event that has already occurred. |
| `POST /simulate/out-of-order` | Swaps event `version` ordering, intentionally skipping a sequence. |
| `POST /simulate/concurrent` | Unleashes 5 parallel threads racing to overdraft the same account. |
| `POST /simulate/corruption` | Manually alters the loaded state in RAM (bypassing the log) and then triggers the validation suite to prove invariant failures. |

---

## 📚 Local Testing

The backend engine contains a complete suite of Python `pytest` functions that run entirely in-memory, bypassing EventStoreDB entirely to prove the mathematical consistency of the `Projector` layer.

```bash
cd backend
source .venv/bin/activate
pytest -v
```

This suite validates Snapshots, Idempotency, Ordering Violations, Validation Corruptions, and Concurrency across 20 strict test boundaries.

---
<div align="center">
  <i>Designed and developed manually within the hackathon deadlines. 100% Core Logic. No pre-built templates.</i>
</div>
