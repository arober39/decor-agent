# Talk Draft — When Your API Call Takes Five Minutes

**Conference:** API World 2026 — API operations track
**Abstract:** see [cfp-api-world-2026.md](cfp-api-world-2026.md)
**Demo:** this repo (decor-agent), Temporal version
**Assumed slot:** 25 min talk + 5 min Q&A (rescale timings if the slot differs)

---

## Narrative arc

> REST assumptions break → the failure modes are silent → accept that it's a
> workflow with an HTTP face → live proof (crash demo) → three plays + a
> meta-move (survivable → visible → steerable, rehearsal performed not preached)
> → this is a pattern, not a vendor.

One sentence the audience should repeat afterward:
**"A long-running LLM endpoint isn't an API anymore — it's a workflow with an HTTP face, and you have to operate it like one."**

---

## 1. Cold open — the lie in the status code (3 min)

**Slide 1 — Title.**

**Slide 2 — A curl that hangs.** One terminal screenshot: `curl -X POST /api/plan` … cursor blinking. Caption: *"This request will succeed in four and a half minutes. What does your infrastructure do in the meantime?"*

**The thesis line (say verbatim, over the hanging-curl slide):**
> "This talk will not make this request faster. Nothing will. This talk is about what your infrastructure does during minutes that are here to stay."

The five minutes is the **premise, not the problem**: the quest is to make the duration survivable (work outlives the request, crashes don't restart it, humans can wait for free, progress is visible), not short. What you *do* attack is perceived latency, never actual duration.

**Slide 3 — The claim + the promise (~20s).** Big line, alone at top: **"When your API call takes five minutes, the call stops being the unit of work."** Then three promise bullets:
- I will kill a live system on stage — and the user won't notice
- You'll leave with a 3-play operations playbook for long-running LLM endpoints
- Nothing here is vendor-specific

**Speaker note (Slide 3):** deliver the big line as the industry claim, not the app anecdote — "this is where API operations is heading, whether we design for it or not." Do NOT say what the unit of work becomes; that's Slide 9's reveal. The thread: Slide 3 provokes, Slide 9 resolves ("a workflow with an HTTP face"), Slide 21 bookends ("the call was never the unit of work — the workflow is").

**Slide 4 — The assumptions REST quietly makes.**
- Sub-second: gateways, load balancers, and clients all have timeouts tuned for it
- Stateless: any replica can serve any request
- Deterministic: a retry is a repeat
- Stable: behavior only changes when you deploy

**Speaker note:** Don't say "LLM" yet on Slide 4. Let the room recognize their own CRUD stack first, then reveal that a single model call violates all four. Land the personal hook: "I built an interior-design assistant. Ask it to furnish a whole apartment on a budget, and one HTTP request fans out into per-room LLM calls that take minutes. Everything I thought I knew about operating APIs failed silently."

---

## 2. The four silent failures (4 min)

One slide per assumption from Slide 4, knocked down **in the same order**, each ending with the play that fixes it (foreshadowing the playbook):

**Slide 5 — Duration** *(breaks: sub-second)*. A 5-minute request meets a 60-second ALB idle timeout. The *client* gives up; the *work* doesn't. Money is spent on tokens for an answer nobody receives. → *Play 1 (the HTTP layer)*

**Slide 6 — Crash amnesia** *(breaks: stateless)*. Worker dies at room 2 of 3. Minutes of accumulated progress lived in one process, so no replica can pick it up — in-process orchestration restarts from zero: user pays twice, waits twice. → *Play 1 (the execution layer)*

**Slide 7 — Retries don't mean what they used to** *(breaks: deterministic)*. Non-deterministic output breaks the retry contract: same input ≠ same output, so an idempotency key on the request no longer guarantees the response it protects. You must checkpoint *results*, not deduplicate *requests*. → *Play 1 (the retry mutation)*

**Slide 8 — The config treadmill** *(breaks: stable)*. Models deprecate, prompts change weekly, providers have regional bad days — your deploy cycle is none of those speeds. Hardcoded model + prompt means every prompt tweak is a deploy and every provider incident is an outage. → *Play 3 (runtime control)*

**Speaker note:** These four slides ARE the abstract, one claim per slide. Keep each to ~60 seconds; the audience should feel each one as "that's happened to me." Open the section with the callback: *"Remember the four assumptions? Watch them fall — in order."* Note the shape: three of the four failures resolve into Play 1 — that's deliberate, survival is most of the battle. There's also a fifth failure you can't see from any of these slides: the call that succeeds at the HTTP layer and fails semantically. Plant it in one sentence here — "and one more failure is invisible by definition; hold that thought" — it's Play 2's opening.

**Staging note (Slide 6):** put the LangGraph "before" on screen — the hand-rolled `error_handler` retry counter — as the visual for "in-process orchestration." Asset: `docs/talk-assets/01-before-error-handler.png`.

---

## 3. Reframe + demo setup (2 min)

**Slide 9 — The reframe.** "Stop calling it an API. It's a workflow with an HTTP face." (This resolves Slide 3's open question: the workflow is the unit of work.) The HTTP layer's only jobs: **start** work, **report** progress, **accept** decisions, **deliver** results. Everything else lives in a durable execution layer.

**Slide 10 — The demo app, honestly.** Architecture diagram (three boxes: FastAPI face → Temporal service → worker hosting workflow + activities).

**The 15-second disclaimer (say it verbatim, early):**
> "I built this on Temporal because it's the easiest way to show you durability *failing to fail* live on stage. Hold your vendor objections — at the end I'll map every play onto Step Functions, Restate, and friends. Nothing I claim today is Temporal-specific."

**Speaker note:** This inoculates the talk against "vendor pitch" perception and pre-answers the most predictable Q&A question.

---

## 4. THE CRASH DEMO (6 min) — the centerpiece

Runbook basis: [TEMPORAL.md](../TEMPORAL.md) §"The crash demo". Three visible surfaces, named consistently below: **the app UI** (the decor agent at `/temporal` — what the user sees), **the worker terminal**, and **the Temporal UI** (:8233 — the event history).

**Beat 1 — Start (1 min).** In the app UI: *"plan my whole apartment, budget $8,000."* Narrate the fan-out as the per-room progress widget moves: "one HTTP POST returned immediately with a workflow ID; the real work is fanning out, one activity per room."

**Beat 2 — Kill (1 min).** Mid-fan-out, Ctrl-C the worker **on the projector**. Point at the app UI: the loading widget keeps breathing; no error surfaces. Point at the Temporal UI: execution still **Running**. Line: *"I just did to my own app what a bad deploy, an OOM kill, or a spot-instance reclaim does to yours weekly. Watch what the user sees: nothing."* Then the rehearsal seed (pays off in the close): *"By the way — I've killed this worker fifty times in rehearsal, which is the only reason I'm calm killing it in front of you. Your infrastructure deserves the same courtesy. We'll come back to that."*

**Beat 3 — Resurrect (2 min).** `python -m app.worker`. Narrate replay from the event history in the Temporal UI: completed rooms are **not re-executed** — their results come from history; only the interrupted room resumes. *"No progress lost, no work repeated, no double token spend."*

**Beat 4 — The human wait (2 min).** Plan finishes → workflow **parks** for approval (`wait_condition`). Kill and restart the worker *again* while parked: still fine. *"This wait costs nothing and could last a week. Where does a paused request live in your stack? Here, it's a row of event history."* Approve → shopping list → done.

**Wait-time riffs (~30s each — say these while requests run; never stand silent at a spinner):**

- *While the fan-out runs (Beat 1):* "While the rooms plan themselves, look at what's accumulating in the Temporal UI — every one of these rows is a checkpoint. Activity scheduled, activity started, activity completed, each with its inputs and outputs. This isn't logging; it's the workflow's actual memory. When I kill the worker in a minute, this table is the only thing that needs to survive — and it doesn't live in my process. Notice too that the three rooms are running concurrently — that's one activity per room, each retried independently if it fails. If the kitchen times out, the living room doesn't care."

- *While the fan-out runs (spare, if needed):* "Worth noting what this request costs while we wait: three rooms, each a full model call, maybe thirty seconds and a few cents each. That's the real reason crash amnesia hurts — restarting from zero isn't just slow, it's a bill. Every pattern in the playbook exists because these minutes have a price tag attached. Multiply this one request by a few thousand users a day and the difference between 'resume' and 'restart' stops being an architecture debate and becomes a line item your finance team can see."

- *While the resumed room finishes (Beat 3):* "Notice what the restarted worker did NOT do — it didn't call the model again for the two finished rooms. It replayed history, saw 'living room: done, bedroom: done,' and picked up only the room that was in flight. Replay is cheap — it's reading a table. Regenerating is expensive — it's paying for tokens twice and getting a different answer the second time. This is also why the workflow code has to be deterministic: replay only works if re-running the orchestration makes exactly the same decisions in the same order. That's the one discipline this model asks of you, and it's the price of everything you're watching."

- *While the shopping list generates (Beat 4):* "One more model call, synthesizing everything you approved into a shopping list. Same durability rules apply — if the worker died right now, the approved plans are already in history; only this last step would resume. And notice: your approval is in that history too. Signals are events like everything else, which means the audit trail of who approved what comes for free. In a regulated shop, that's not a nice-to-have — 'show me every plan a human signed off on, and when' is a query against data you already have, not a logging project you haven't started."

- *Emergency riff (any unexpectedly long wait):* "This pause? This is the talk. Right now a load balancer somewhere would be deciding whether to kill this connection. The user's spinner is still moving because progress lives in the workflow, not the socket. If the wait annoys you, good — now imagine it with nothing underneath. Every team that operates LLM endpoints has sat in exactly this silence and made a choice: engineer for the wait, or hope it stays rare. The whole playbook is what 'engineer for the wait' looks like written down."

**Contingency plan (do not skip in rehearsal):**
- Pre-record the full demo as backup video; play it if wifi/LLM misbehaves.
- Keep a completed workflow from rehearsal in the Temporal UI to show history if live run fails.
- LLM latency spike mid-demo: that's not a failure, narrate it — "this is the five minutes in the title."

---

## 5. The playbook — three plays and a meta-move (8 min)

**Slide 11 — Playbook framing (~15s).** **"The playbook is three plays — plus one thing you already watched. We'll name it at the end."** Each play is a tool-neutral claim slide + evidence from this repo (one evidence slide each for Plays 2 and 3; Play 1 carries enough to earn two). The plays form a chain, not a list: survivable → visible → steerable, and each needs the one before it (you can't canary without metrics; you can't degrade without a lever).

### Play 1 — Make the work survive everything, including its own API (3.5 min, 3 slides)

**Slide 12 — Play 1 claim (~60s):** The unit of work must outlive whatever executes it — and "whatever executes it" includes the HTTP connection. The client disconnecting at minute four and the worker OOMing at minute four are the same event: something executing died, and the work shouldn't care.

**Slide 13 — Play 1 evidence A: the two layers of the same principle (~75s):**
- *At the HTTP boundary* — never let one request carry minutes of work. Four verbs: **start** (returns an ID immediately), **status** (cheap progress), **decide** (accept human/system input mid-flight), **result** (fetch when done). Evidence: `server.py`'s four `/api/temporal/plan` endpoints. Asset: `docs/talk-assets/02-http-face-four-verbs.png`.
- *At the execution layer* — split code into **deterministic orchestration** (replayable, no I/O) vs **checkpointed side effects**; durability, retries, and crash-resume fall out of the split. Evidence: `workflow.py` vs `activities.py`, and the crash the audience just watched.

**Slide 14 — Play 1 evidence B: the retry mutation + the reliability stack (~75s):** a retry of an LLM call is a *re-roll*, not a repeat — idempotency keys can dedupe the request but can't reproduce the response. So the play is **checkpoint results, never regenerate by accident**. The three stacked reliability layers:
1. inside the activity — multi-model fallback (`_invoke_with_fallback`) absorbs provider hiccups
2. per activity — declarative `RetryPolicy` (1s, 2×, 3 attempts) + 90s timeout replaces the hand-rolled error node
3. across process death — replay from event history (what the demo proved)

Asset: `docs/talk-assets/03-retry-policy.png` (the `RetryPolicy` + checkpointed `execute_activity`).

Close the slide with the bug-class admission (~30s, spoken over the same visual): the human wait (`wait_condition` + signals) and the subtle bug avoided in `workflow.py`: don't reset the decision before parking — a signal can arrive while rooms are still planning, and clearing it parks the workflow forever. Asset (optional build): `docs/talk-assets/04-durable-wait.png` (the parked `wait_condition` with the don't-reset comment).

**Speaker notes (Play 1):**
- Honesty beat on the four-verbs slide: `/result` blocks for demo simplicity — say so, and name what production does instead (poll or webhook).
- Line to land after the bug-class admission: *"Durable execution has its own bug classes. The playbook includes knowing them."*

### Play 2 — Watch the new dimensions, not just the old ones (2.5 min, 2 slides)

**Slide 15 — Play 2 claim (~75s):** RED metrics still apply, but LLM calls add three dimensions your dashboards don't have yet: **cost per call, quality of output, and which prompt/model version served it**. An LLM call can succeed at the HTTP layer and fail at the semantic layer — and no status code will tell you. Health becomes per-version, not per-endpoint: the same route can be healthy on one prompt and sick on another simultaneously.

**Slide 16 — Play 2 evidence (~75s):** every activity tracks duration/tokens/success against the config version that served it (`get_completion_config` + `track_*`); the `snapshot` query that fed the live progress widget during the crash; response metadata carrying `models_used` and `routed_to`. Asset: `docs/talk-assets/05-config-per-call.png`.

The dark-side coda (~40s, spoken over the same slide or a ciphertext screenshot build): visibility's cost — everything you persisted is now **data at rest**, including user PII that arrived in a chat message. Your event history is an observability superpower and a compliance surface in the same table. Evidence: `codec.py` — client-side AES-256-GCM payload codec; the Temporal UI shows `binary/encrypted` ciphertext. Secrets never enter workflow args at all (API key read inside activities). Asset: `docs/talk-assets/06-codec-encode.png`.

**Speaker note (Play 2):** open by paying off the seed planted in section 2: *"here's the fifth failure I promised — the invisible one."*

### Play 3 — Runtime control: put the volatile things behind runtime levers (2 min, 2 slides)

**Slide 17 — Play 3 claim (~60s):** model, prompt, and parameters are the most volatile parts of the system and the least likely to be behind a lever. Put them under runtime control — externalized, versioned, with Play 2's metrics attached to every version — and one mechanism buys three capabilities:
1. **Safe change** — canary a prompt/model change on a traffic slice, watch the metrics, rollback is one click
2. **Cost control** — tier traffic: which segment gets which model is an operational decision (spend management), made at runtime
3. **Deliberate degradation** — the quality knob classic APIs never had: during a provider incident, downgrade model/output length for low-priority traffic instead of failing everyone

**Slide 18 — Play 3 evidence + war story (~60s):** per-call config resolution with code-default fallback in every activity — and the live fix: this app's routing prompt made every trivial question consult a specialist (three LLM calls for a one-sentence answer, 8.3s). The fix was a prompt edit in the config dashboard — the running server picked it up mid-session, no deploy, no restart: **8.3s → 3.3s**. The same metrics that debug failures expose gold-plating. *Accept the irreducible minutes — then make every second in them earn its keep.*

**Speaker note:** This is the employer-adjacent section — keep it pattern-first ("externalize + measure + roll back"), name the vendor once as "what I used," same as Temporal.

### The meta-move — named, not presented

Rehearsal never gets its own section; it got *performed* (see the callout line in the demo, section 4). Callback on the closing slide: **"The fourth thing was the demo itself."**

**Slide 19 — The drill list.** LLM-ops drills, one slide: provider brownout (do the fallbacks actually fire?), model deprecation day, prompt regression that passed eval, cost runaway (a retry loop on an expensive call is a billing incident), and the minute-four disconnect.

---

## 6. Ecosystem slide + close (2 min)

**Slide 20 — "Same playbook, other spellings."** The play × tool matrix (rows grouped: 1–4 are Play 1, 5 is Play 2, 6 is Play 2's coda):

| Play | Temporal (demoed) | Step Functions | Restate | Azure Durable Functions | DBOS |
|---|---|---|---|---|---|
| Start/status/decide/result face | FastAPI + client SDK | StartExecution / task tokens | HTTP ingress (built in) | HTTP APIs (built in) | your app + library |
| Checkpointed side effects | activities | Lambda task states | `ctx.run` | activity functions | `@step` → Postgres |
| Park for a human | `wait_condition` + signal | `.waitForTaskToken` | durable promise | external event | recv/event |
| Fan-out w/ per-item retry | `gather` over activities | `Map` state | parallel durable calls | fan-out/fan-in | queued steps |
| Live progress query | `@workflow.query` | ⚠️ DIY (DynamoDB/history) | shared state handler | custom status | query the DB |
| Encrypted history | payload codec | KMS (server-side) | ⚠️ DIY | ⚠️ DIY | your Postgres, your keys |

One line per ⚠️ only; don't walk the whole table. Message: *"Pick your operational posture — run-it-yourself, managed JSON, single binary, or just-a-library. The playbook is the same."*

**Slide 21 — Close.** The three plays as three lines, then the rehearsal callback ("the fourth thing was the demo itself" — gesture back at Slide 19). Final bookend, paying off Slide 3's claim: *"Classic API operations spent decades making calls short, uniform, and repeatable. LLM operations starts by admitting your calls are long, unique, and expensive — and rebuilds every play on top of that admission. When your API call takes five minutes, the call was never the unit of work. The workflow is."* → repo QR code.

**Slide 22 — Q&A (leave up for the full Q&A).** Title: **"Ask me about…"** — keyword bank from the talk, arranged loosely, plus the repo QR again:
- the worker kill (or: killing it twice)
- retries are re-rolls · checkpoint results
- the four verbs: start / status / decide / result
- deterministic replay — the one discipline
- the five timeouts between user and model
- event history as memory… and as PII at rest
- the 8.3s → 3.3s prompt fix, no deploy
- canary a prompt · degrade by model tier
- Step Functions / Restate / DBOS mapping
- the drills: brownout, deprecation day, cost runaway
- streaming vs polling
- "isn't this over-engineering?"

**Speaker note (Slide 22):** every keyword maps to an entry in Q&A prep below — the slide is bait for questions you've already rehearsed. Including "isn't this over-engineering?" on the slide defuses it: naming the skeptic's question invites it on your terms. Keep it up the whole Q&A; silence-breaking line if no hands: *"Someone has to ask about the second kill — it's the best one."*

---

## Q&A prep

- **"Why not Step Functions / [tool]?"** → point back at the matrix; "same playbook, different operational posture — I demoed the one I could kill on stage."
- **"Isn't this over-engineering for a chatbot?"** → the trigger is *duration × cost × fan-out*, not LLMs per se; a 900ms single call doesn't need this. The moment one request = minutes of paid compute, amnesia is a billing problem.
- **"What about streaming/SSE instead of polling?"** → orthogonal: streaming is a delivery channel on the status/result verbs; it doesn't solve crash amnesia or the human wait.
- **"Doesn't streaming already beat the timeouts?" / "Can't you just raise the ALB timeout?"** → partially, and that's the trap. Most of these timeouts are *idle*-based, so streaming keeps the connection alive by trickling bytes — but it only masks the timeout failure; the work still dies with the worker and still can't park for a human. Raising the timeout is whack-a-mole across five layers (LB, gateway, proxy, CDN, client), some of which you don't control — the 29s API Gateway cap isn't yours to raise. Fix the unit of work, not the timeout.
- **"Idempotency keys?"** → still useful at the start verb (dedupe workflow starts, e.g. workflow ID = request key); what they can't do is make regenerated non-deterministic output identical — that's why you checkpoint results.
- **"Doesn't the LLM call itself remain non-durable?"** → yes — an activity that dies mid-call is retried, tokens re-spent; durability's unit is the activity boundary. Mitigations: shorter activities, provider-side idempotency where offered, checkpoint between steps.
- **"What counts as non-deterministic in workflow code?"** → anything that could differ on replay: clocks, randomness, network calls, iteration order of unordered collections, environment reads. All of it moves into activities (checkpointed) or the platform's deterministic substitutes (workflow-safe time/random). The linter/runtime catches most of it; the discipline is architectural, not heroic.
- **"Why encrypt instead of redacting PII before it enters the workflow?"** → do both if you can, but redaction is a classifier (it misses), while encryption is a guarantee (ciphertext at rest regardless of what the classifier missed). Also redaction destroys data the LLM may legitimately need ("ship it to my address"). Encrypt the history; redact where the product allows.
- **"Temporal operational burden?"** → real; that's the honest trade in the matrix (vs Step Functions fully-managed / Restate single binary / DBOS library). Don't be defensive.
- **Restate spike** (pinned): if asked directly whether the demo runs on Restate — "the mapping is clean and it's on my list; today I can vouch for the patterns, not that port."

---

## Prep checklist

- [ ] Timings sum to 25 (3+4+2+6+8+2); rescale proportionally if the slot differs
- [ ] Code screenshots live in `docs/talk-assets/` (01–06) and in Canva under the "apiworld presentation" folder; the deck is the Canva design "When Your API Call Takes Five Minutes — API World 2026"
- [ ] Rehearse the kill: mid-fan-out timing (rooms 1–2 done, 3 in flight reads best)
- [ ] Record backup video of full demo; keep a rehearsal run's history in the Temporal UI
- [ ] Terminal fonts ≥ 18pt; light theme for projectors; Temporal UI zoomed
- [ ] Pre-warm: dev server + worker + server running before walking on stage
- [ ] `ENCRYPTION_KEY` set so Play 2's ciphertext view is one click in the Temporal UI
- [ ] Decide streaming-vs-polling one-liner (Q&A) matches what the repo actually does (polling)
- [ ] Speaker bio slide (optional Slide 23, or conference-provided intro) + repo QR on Slides 21 and 22
- [ ] Every Slide 22 keyword has a rehearsed answer in Q&A prep — check the mapping before finalizing the deck
