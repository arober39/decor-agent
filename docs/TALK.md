# Talk: "Temporalizing a LangGraph AI agent"

10–15 min walkthrough for a developer / Temporal‑customer audience. Slabs are timed; **bold** lines are the ones to say out loud.

---

## 0. Cold open (1 min)

> **"I built an interior‑design AI agent. It worked great — until I asked it to do something real: plan a whole apartment, fan out across rooms, then wait for a human to approve before spending the budget. That's where a normal request/response app falls apart, and it's exactly where Temporal shines. Let me show you the before and after."**

Show the two tabs in the UI: **Decor Agent** (LangGraph) and **Decor Agent (Pro)** (Temporal).

---

## 1. The before, and why it hurts (2 min)

The original is a LangGraph state machine — `input_guard → agent → tools → error_handler → response`. It's clean, but it's **in‑process and single‑request**:

- **Crash = amnesia.** Die mid‑request and every step is lost. Nothing remembers "we already planned the living room."
- **I hand‑rolled reliability.** There's literally an `error_handler` node counting retries. Timeouts, backoff, idempotency — my problem.
- **It can't wait.** "Here's the plan, approve it?" has nowhere to live between question and answer. The classic fix is a DB flag + a cron poller.

> **"Every backend engineer has written this plumbing — retry loops, timeout handling, a state machine in a database to remember which step we're on. Temporal exists to delete all of that."**

---

## 2. The 90‑second vocabulary (2 min)

Just enough to follow along:

- **Workflow** — my business process as ordinary code. The orchestrator. *The recipe.*
- **Activity** — a single real‑world action: call the LLM, send an email. Side effects live here, and **only** here. *The cooking.*
- **Worker** — a process *I* run that executes the workflow + activity code. **"Temporal doesn't run your code — your workers do."**
- **Task Queue** — the channel workers poll. (Mine is `decor-agent`.)
- **Signal** — async message *into* a running workflow ("approved!").
- **Query** — sync read *out* of a workflow ("what phase are you in?"). **Signals write, queries read.**
- **Event History** — the ordered log of everything that already happened. The durable backbone.

**The three constructs, in one screen** (`app/worker.py`):

```python
# app/worker.py — YOU run this process; it executes the workflow + activities.
client = await Client.connect("localhost:7233")
with ThreadPoolExecutor(max_workers=10) as activity_executor:
    worker = Worker(
        client,
        task_queue="decor-agent",
        workflows=[DecorAgentWorkflow],
        activities=[agent_turn, run_tool, extract_rooms, plan_room,
                    build_shopping_list],
        activity_executor=activity_executor,   # sync activities need a thread pool
    )
    await worker.run()
```

---

## 3. The magic trick: replay & determinism (3–4 min) — *centerpiece*

> **"Temporal gives your code durability by re‑running it from the top after a crash — and replaying the recorded history of what already happened, so it fast‑forwards back to exactly where it left off without redoing the real work."**

Walk it:
1. As the workflow runs, every step — *called this activity, got this result; timer fired; received this signal* — is appended to **Event History**, persisted by the service.
2. Crash. A new worker picks it up and **replays from line one** — but when it hits an activity it already ran, Temporal hands back the recorded result instead of re‑running it.
3. Replay catches up, execution continues live. From the code's view, the crash never happened.

**Why workflow code must be deterministic:** replay only reconstructs the right state if the code makes the same decisions every time. So inside a workflow — no `datetime.now()`, no `random`, no network. Those go in **activities**.

> **"The workflow is the recipe; the activities are the cooking. Deterministic orchestration you can replay, plus messy real‑world work that runs once and gets recorded. That split is the whole trick."**

Show `app/workflow.py`: no LLM calls, no clock — just orchestration. It only *decides*; side effects go over `execute_activity`:

```python
# app/workflow.py — deterministic: no LLM, no datetime.now(), no I/O.
# It hands work to activities with a timeout + retry policy, and awaits results.
rooms = (await workflow.execute_activity(
    extract_rooms,
    ExtractRoomsInput(message=message, context_key=context_key),
    start_to_close_timeout=ACT_TIMEOUT,   # = timedelta(seconds=90)
    retry_policy=RETRY,                   # = RetryPolicy(backoff=2.0, max_attempts=3)
)).rooms
```

Then `app/activities.py`: every real-world side effect lives here. (Sync `def` because the LLM call blocks — the worker runs it in the thread pool, exactly like Temporal's `hello_activity` sample.)

```python
# app/activities.py — the ONLY place the network / LLM is touched.
@activity.defn
def plan_room(inp: RoomPlanInput) -> RoomPlan:          # single dataclass in/out
    ...
    user = f"Room: {inp.room}\nBudget: {inp.budget}\n\nPlan this room."
    text, model = _invoke_with_fallback(                # the actual Claude call
        cfg.system_prompt, user, cfg.model, cfg.max_tokens, cfg.temperature)
    return RoomPlan(room=inp.room, plan_text=text,
                    latency_ms=latency_ms, model_used=model)
```

---

## 4. How I broke it apart (2–3 min)

My rationale, node‑by‑node:

- **LangGraph nodes that *do* things → activities.** `agent`, the tool calls, room planning, the shopping list. They call the LLM, so they're non‑deterministic → activities. *I reused the exact same domain code* — `llm.py`, the prompts, the flag resolution. Only orchestration moved.
- **The control flow → the workflow.** Routing, the tool loop, the fan‑out. Pure decisions.
- **The deterministic guard → stays inline.** Input validation is a pure function of its inputs, so it runs in the workflow itself — no activity needed. (If it ever called a PII service, it'd *have* to become an activity. Good teaching moment.)
- **Two things LangGraph couldn't do, now trivial:**
  - **Fan‑out** — `asyncio.gather` over one `plan_room` activity per room; Temporal records and replays completion order.
  - **Human‑in‑the‑loop** — `await workflow.wait_condition(...)` parks the workflow for **seconds or days** until an `approve` / `reject` / `tweak_budget` **signal** arrives. A `snapshot` **query** drives the live UI while it's parked.

**Fan-out** (`app/workflow.py`):

```python
# app/workflow.py — one activity per room, run concurrently, gathered.
# Temporal records each completion in history and replays it identically.
tasks = [asyncio.create_task(self._plan_one(r, budget, context_key))
         for r in rooms]
plans: list[RoomPlan] = await asyncio.gather(*tasks)
```

**Human-in-the-loop: signals in, query out, durable wait** (`app/workflow.py`):

```python
# app/workflow.py
@workflow.signal                         # pushed INTO a running workflow
def approve(self) -> None:
    self._decision = "approve"

@workflow.query                          # read OUT, no side effects — drives the live UI
def snapshot(self) -> dict:
    return {"phase": self._phase, "rooms_done": list(self._rooms_done), ...}

# ...inside run(): park here for seconds or days until a decision lands
await workflow.wait_condition(
    lambda: self._decision is not None or self._new_budget is not None)
```

---

## 5. The challenge / gotcha that taught me Temporal (1–2 min)

> **"Durable, asynchronous signals change how you reason about state — and I learned that the hard way."**

The whole‑home loop reset the decision state right before `wait_condition`. Feels harmless. But a signal can arrive **while the rooms are still planning** — and the reset wiped it. The workflow then parked forever and tripped the execution timeout.

```python
# ❌ BEFORE — resets a signal that may have already arrived during planning → parks forever
self._decision = None
self._new_budget = None
await workflow.wait_condition(
    lambda: self._decision is not None or self._new_budget is not None)
```

```python
# ✅ AFTER — never clear the decision pre-wait; only consume a budget tweak after using it
await workflow.wait_condition(
    lambda: self._decision is not None or self._new_budget is not None)
if self._new_budget is not None:
    budget = self._new_budget
    self._new_budget = None        # consume, then re-plan
    continue
```

The lesson: in a durable system, a signal isn't "an event I'm waiting for" — it's **state that may already be there**. And the tests caught it because the time‑skipping environment replays the exact race in milliseconds — no API key, no server:

```python
# test_workflow.py — the "days-long" human wait completes in milliseconds.
async with await WorkflowEnvironment.start_time_skipping() as env:
    async with Worker(env.client, task_queue=TASK_QUEUE,
                      workflows=[DecorAgentWorkflow], activities=MOCKS):
        handle = await env.client.start_workflow(
            DecorAgentWorkflow.run,
            args=["plan my whole apartment", "$8000", "test", 2000],
            id=_wf_id(), task_queue=TASK_QUEUE)
        await handle.signal(DecorAgentWorkflow.approve)
        result = await handle.result()
        assert "Shopping List" in result["response"]
```

---

## 6. Why the Temporalized version wins (1 min)

- **Crash‑proof** — kill the worker mid‑plan, restart, it resumes. (Live demo, section 7.)
- **Reliability is declarative** — `RetryPolicy` + timeouts replaced my `error_handler` node.
- **Long waits are free** — human approval needs no DB flag, no poller.
- **Concurrency is one line** — fan‑out via `gather`, partial failures retried independently.
- **Observability built in** — every step is in the Web UI; the `snapshot` query powers the live status panel.

**Trade‑offs I'll own:** you run more moving parts (a service + workers); workflow code lives under the determinism constraint; and there's a real learning curve to "this code may run many times via replay." For a single fast request, LangGraph is simpler — Temporal earns its keep the moment you need durability, long waits, or fan‑out.

---

## 7. Live demo (1–2 min)

1. Start a whole‑home plan → watch it fan out, then **park** for approval (Web UI shows *Running*).
2. **Ctrl‑C the worker.** Workflow is untouched in the service.
3. **Restart the worker.** It replays history and resumes — no lost progress, no repeated work.
4. Send `approve` → shopping list returned.
5. Open http://localhost:8233 and walk the event history: activity completions, the signal, the timer.

---

## 8. How I'd teach this to developers (close, 30 sec)

> **"Start from the pain they already feel — the retry loop and the DB state machine they've written ten times. Give them the recipe/cooking split as the one mental model. Then show, don't tell: kill the worker live. Durability you can *watch* recover is worth a hundred slides."**

Point them at: the [Python SDK docs](https://docs.temporal.io/develop/python), [samples‑python](https://github.com/temporalio/samples-python), and this repo's `TEMPORAL.md` runbook.

---

### Misconceptions to preempt if asked
- *"It's just a fancy queue/Celery."* No — a queue moves tasks; Temporal gives durable state + replay‑based recovery across many steps.
- *"Temporal runs my code."* No — **your workers** run it, on your infra. The service orchestrates and stores history.
- *"Activities are exactly‑once."* At‑least‑once with retries → **make activities idempotent.** The *workflow* gives once‑to‑completion; an activity attempt can repeat.
