# Decor Agent → Temporalized

This repo started as a [LangGraph](https://langchain-ai.github.io/langgraph/) interior‑design agent (the **before**). This document covers the **after**: the same domain logic re‑expressed as a [Temporal](https://docs.temporal.io/) application, so the orchestration becomes **durable, retryable, and human‑in‑the‑loop‑aware** without rewriting the business logic.

> Both versions ship in the repo and run side‑by‑side. The original LangGraph agent still serves `/api/chat` and the `/` UI. The Temporal version serves `/api/temporal/*` and the `/temporal` UI.

---

## TL;DR

| | Before (LangGraph) | After (Temporal) |
|---|---|---|
| **Orchestration** | In‑process graph (`app/graph.py`) | Workflow replayed from event history (`app/workflow.py`) |
| **State on crash** | Lost — restart from scratch | Durable — resumes from the last recorded event |
| **Retries / timeouts** | Hand‑rolled `error_handler` node, bounded counter | Declarative `RetryPolicy` + activity timeouts |
| **Long / human wait** | Not possible (request/response only) | `workflow.wait_condition` — parks for seconds or days |
| **Concurrency** | Sequential nodes | Fan‑out: one activity per room, gathered |
| **Live status** | None | `@workflow.query` snapshot polled by the UI |
| **Side effects** | Mixed into nodes | Isolated in `@activity.defn` functions |

---

## The original problem (before)

`run_agent()` invokes a compiled LangGraph: `input_guard → agent → execute_tools → error_handler → agent → response_formatter`. It works, but it is an **in‑process, single‑request** machine:

- If the process dies mid‑request, **all progress is lost** — there is no durable record of "we already called the room planner for the living room."
- Reliability is **hand‑rolled**: the `error_handler` node counts retries up to `max_retries`, then gives up. Timeouts, backoff, and idempotency are the developer's problem.
- It **can't wait**. A request that needs human approval ("here's the plan — approve it?") has nowhere to live between the question and the answer. You'd bolt on a database flag and a polling job.
- **Fan‑out** across many rooms would mean manual threading + manual partial‑failure handling.

These are exactly the problems Temporal's durable execution model removes.

---

## The Temporalized architecture (after)

Three Temporal constructs, mapped to this app:

```
                    ┌─────────────────────────────────────────────┐
   POST /api/        │  Temporal Service (dev server :7233)         │
   temporal/plan ───▶│  • persists Event History                    │
                    │  • schedules tasks onto task queue           │
                    └───────────────┬─────────────────────────────┘
                                    │  task queue: "decor-agent"
                                    ▼
                    ┌─────────────────────────────────────────────┐
                    │  Worker  (app/worker.py)                     │
                    │  hosts:                                      │
                    │   • DecorAgentWorkflow   (deterministic)     │
                    │   • activities (LLM / network / side effects)│
                    └─────────────────────────────────────────────┘
```

### Workflow — `app/workflow.py` (`DecorAgentWorkflow`)
Pure, deterministic orchestration. **No LLM calls, clock, randomness, or I/O** — every side effect is delegated to an activity. This is the LangGraph control flow lifted into Temporal:

- `@workflow.run` — validates input (a deterministic, pure guard runs inline), then routes to either the single‑turn agent loop or the whole‑home plan.
- **Signals** (`approve`, `reject`, `tweak_budget`) — human‑in‑the‑loop decisions pushed *into* a running workflow.
- **Query** (`snapshot`) — read‑only live status (phase, per‑room progress, draft plans) pulled *out* without disturbing the run.
- **Durable wait** — `await workflow.wait_condition(...)` parks the workflow until a decision signal arrives. Survives worker restarts.
- **Fan‑out** — one `plan_room` activity per room, each wrapped so it marks itself done the moment it returns (driving the live per‑room progress in the snapshot query), then gathered with `asyncio.gather`. The concurrency is plain asyncio; what Temporal adds is that each room is a durable, independently‑retried activity, and the completion order is recorded in history so replay is deterministic.

### Activities — `app/activities.py`
Every non‑deterministic, side‑effecting operation: `agent_turn`, `run_tool`, `extract_rooms`, `plan_room`, `build_shopping_list`. Each:
- takes a single `@dataclass` input and returns a `@dataclass` (serializes cleanly into event history),
- reuses the **exact same** domain code as the LangGraph nodes (`llm.py`, `flags.py`, the prompts) — only the orchestration moved,
- carries a multi‑model fallback so a single provider hiccup is retried internally before Temporal's `RetryPolicy` takes over.

### Worker — `app/worker.py`
Connects to `localhost:7233`, registers the workflow + all activities on the `decor-agent` task queue, and polls. **Temporal doesn't run your code — this worker does.** Run as many as you like for scale/HA.

---

## Runbook — clone to crash‑demo

### Prerequisites
- Python 3.12, a virtualenv with `pip install -r requirements.txt`
- An `ANTHROPIC_API_KEY` in `.env`
- The Temporal CLI (`brew install temporal`) — provides the dev server + Web UI

### Three processes (three terminals)

**1 — Temporal dev server** (includes the Web UI at http://localhost:8233):
```bash
temporal server start-dev
```

**2 — The worker** (hosts the workflow + activities):
```bash
source venv/bin/activate
python -m app.worker
```

**3 — The API + UI server:**
```bash
source venv/bin/activate
python server.py            # http://localhost:8000/temporal
```

### Drive it

**Single‑turn durable chat:**
```bash
curl -X POST http://localhost:8000/api/temporal/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What color goes with walnut floors?"}'
```

**Whole‑home plan with human approval:**
```bash
# 1) start it — returns a workflow_id
curl -X POST http://localhost:8000/api/temporal/plan \
  -H 'Content-Type: application/json' \
  -d '{"message":"plan my whole apartment","budget":"$8000"}'

# 2) watch live status (phase + per-room progress)
curl http://localhost:8000/api/temporal/plan/<workflow_id>/snapshot

# 3) send a decision: approve | reject | tweak_budget
curl -X POST http://localhost:8000/api/temporal/plan/<workflow_id>/decision \
  -H 'Content-Type: application/json' \
  -d '{"decision":"approve"}'

# 4) fetch the final result
curl http://localhost:8000/api/temporal/plan/<workflow_id>/result
```
You can do all of this from the UI at **http://localhost:8000/temporal**, and inspect every event in the **Temporal Web UI at http://localhost:8233**.

> Signals can also be sent with the raw CLI, e.g.
> `temporal workflow signal --workflow-id <id> --name approve`.

### The crash demo
1. Start a whole‑home plan (it fans out, then **parks** on `wait_condition` waiting for your approval).
2. **Kill the worker** (Ctrl‑C in terminal 2) while it's parked — or mid‑fan‑out.
3. The workflow is untouched in the Temporal Service; the Web UI shows it still **Running**.
4. **Restart the worker** (`python -m app.worker`). It replays the event history, restores state, and continues exactly where it left off.
5. Send `approve` — the plan completes. **No progress was lost and no work was repeated.**

---

## Testing

`test_workflow.py` uses Temporal's time‑skipping test environment, so the "days‑long" human wait completes in milliseconds and no API key or Temporal server is required:

```bash
python -m pytest test_workflow.py -v      # 6 passed
```

- `WorkflowEnvironment.start_time_skipping()` runs an in‑memory server that fast‑forwards durable timers.
- Activities are **mocked** by registering same‑named stubs (`@activity.defn(name="plan_room")`), isolating workflow logic from the LLM.
- The human‑in‑the‑loop tests start the workflow, send a signal, and assert the result — exercising fan‑out → durable wait → signal → shopping list deterministically.

---

## Security posture

Temporal is a durable‑execution platform, **not** a security layer — but "Temporalizing" an app *changes its security surface*, so this is a deliberate part of the design.

**The key fact:** Temporal records every workflow input, activity input/output, signal payload, and result in the **Event History**, persisted in the Service's database and visible in the Web UI. Anything passing through a workflow or activity is therefore **stored at rest**.

What this app does, mapped to the standard Temporal practices:

| Practice | How it's handled |
|---|---|
| **Secrets never in workflow inputs** | ✅ The `ANTHROPIC_API_KEY` is read **inside activities** (`get_settings()` → `get_llm`), never passed as a workflow arg. Workflow args are only `[message, budget, context_key, max_input_length]` — no secrets reach event history. |
| **Encryption at rest** | ✅ A custom **AES‑256‑GCM payload codec** (`app/codec.py`) sits in the data converter and encrypts every payload **client‑side** before it leaves the worker/server. The Service only ever stores ciphertext. This directly closes the PII gap below. |
| **Activities as the security boundary** | ✅ Every external call (Claude, LaunchDarkly) lives in an activity — input validation, credentials, and egress all sit at that boundary. |
| **Replay‑safe logging** | ✅ Activities use `activity.logger`; the workflow logs no secrets. |
| **Errors don't leak internals** | ✅ The `/api/temporal/*` handlers log `str(exc)` server‑side and return a generic `{"detail": ...}` to the client. |

**The PII consideration this app specifically raises:** the `input_guard` *detects* PII (email/phone/SSN) but deliberately **does not block** it — so a user message containing PII becomes the workflow input. Without encryption that PII would sit in event history in plaintext. The payload codec is the fix: with `ENCRYPTION_KEY` set, that message is ciphertext at rest.

### Using the codec

```bash
# generate a 32-byte key and add it to .env (gitignored)
python3 -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
# ENCRYPTION_KEY=<paste>
```

Restart the worker + server. The worker logs `encryption=True`; in the Web UI the input/result payloads now show as `binary/encrypted` base64 ciphertext instead of readable text. Toggle by removing `ENCRYPTION_KEY` and restarting. The time‑skipping tests use their own environment with no codec, so they stay green and unencrypted.

**Operational caveats (worth naming):**
- The Web UI/CLI can't decrypt without the key — viewing decrypted payloads in the UI requires running a **codec server**, out of scope here.
- **Key rotation:** starting a workflow with one key then restarting with a different/absent key breaks that workflow's replay. Finish or terminate in‑flight workflows before rotating.

**Consciously deferred (local‑demo scope, production hardening):** mTLS between workers and the Service (mandatory on Temporal Cloud), namespace isolation per environment/tenant, and authn/authz on the `/api/temporal/*` endpoints.

---

## File map (Temporal additions)

```
app/workflow.py     # DecorAgentWorkflow — deterministic orchestration, signals, query
app/activities.py   # @activity.defn functions — all LLM / side-effecting work
app/worker.py       # Worker process: registers workflow + activities on "decor-agent"
app/codec.py        # AES-256-GCM payload codec — encryption at rest (event history)
server.py           # /api/temporal/* endpoints (start, signal, snapshot, result)
web/temporal.html   # "Decor Agent (Pro)" UI — durable chat + whole-home approval
web/temporal.js     # snapshot polling, decision signals, live status widget
test_workflow.py    # time-skipping workflow tests (6 cases, no API key needed)
```

The entire LangGraph "before" (`app/graph.py`, `app/nodes/*`, `app/tools/*`, `app/state.py`) is **untouched** and still runs via `/api/chat`.
