# Decor Agent — LaunchDarkly Demo Runbook

End-to-end playbook for demoing the LaunchDarkly AI iteration loop using the Decor Agent. Covers every setup step, every agent-skill invocation, every variation you'll author, and every moment you'll land on screen.

**Total demo runtime:** ~40 minutes tight, ~60 with Q&A.

---

## Table of contents

- [Pre-demo setup (one-time)](#pre-demo-setup-one-time)
- [Phase 0 — Baseline (2 min)](#phase-0--baseline-2-min)
- [Phase 1 — Kill-switch flag (5 min)](#phase-1--kill-switch-flag-5-min)
- [Phase 2 — Lift prompts into AI Configs (8 min)](#phase-2--lift-prompts-into-ai-configs-8-min)
- [Phase 3 — Variations + targeting (6 min)](#phase-3--variations--targeting-6-min)
- [Phase 4 — Offline evals (5 min)](#phase-4--offline-evals-5-min)
- [Phase 5 — Guarded rollout (6 min)](#phase-5--guarded-rollout-6-min)
- [Phase 6 — Online evals + LLM judges (6 min)](#phase-6--online-evals--llm-judges-6-min)
- [Phase 7 — Generate traffic + dashboard (5 min)](#phase-7--generate-traffic--dashboard-5-min)
- [Appendix A — Writing variation prompts](#appendix-a--writing-variation-prompts)
- [Appendix B — Targeting context attributes](#appendix-b--targeting-context-attributes)
- [Appendix C — Pre-demo checklist](#appendix-c--pre-demo-checklist)

---

## Pre-demo setup (one-time)

Do all of this the day before, not live. The audience watches the outcomes; setup should feel seamless.

### 1. Install LaunchDarkly Python SDKs

```bash
cd decor-agent
source venv/bin/activate
pip install launchdarkly-server-sdk launchdarkly-server-sdk-ai
```

Then update `requirements.txt`:

```
launchdarkly-server-sdk
launchdarkly-server-sdk-ai
```

### 2. Install the LaunchDarkly agent skills

LaunchDarkly publishes its agent skills at `launchdarkly/ai-tooling`. The repo ships a `.claude-plugin/plugin.json` (plugin manifest), **not** a `marketplace.json` (catalog), so `/plugin marketplace add launchdarkly/ai-tooling` fails with *"Marketplace file not found"*.

**Gotcha:** `npx skills add launchdarkly/ai-tooling` works but only installs the top-level `onboarding` skill — it does **not** install the other 18 skills (AI Configs, feature-flags, metrics). The CLI reads a minimal entry, not the full `plugin.json` manifest.

**Recommended path — install as a Claude Code plugin:**

1. In Claude Code, run `/plugin install` and point the interactive installer at the repo `launchdarkly/ai-tooling`.
2. After install, run `/reload-plugins`.

**Fallback — manual symlink:** if the plugin installer misbehaves, clone the repo and symlink each skill directory into `.claude/skills/`:

```bash
git clone https://github.com/launchdarkly/ai-tooling.git
mkdir -p .claude/skills
for dir in ai-tooling/skills/ai-configs/* ai-tooling/skills/feature-flags/* ai-tooling/skills/metrics/* ai-tooling/skills/onboarding; do
  ln -sf "$(pwd)/$dir" ".claude/skills/$(basename $dir)"
done
```

After a proper plugin install, skills are namespaced as `/launchdarkly:<skill-name>` (plugin.json declares `name: launchdarkly`). This runbook uses the short form (`/aiconfig-create`, `/launchdarkly-flag-create`) for readability; with a namespaced install, prepend `/launchdarkly:` — e.g. `/launchdarkly:aiconfig-create`.

Available skill groups after a full install:

- **Feature flags** (`skills/feature-flags/`) — `launchdarkly-flag-discovery`, `launchdarkly-flag-create`, `launchdarkly-flag-targeting`, `launchdarkly-flag-cleanup`
- **AI Configs** (`skills/ai-configs/`) — `aiconfig-create`, `aiconfig-update`, `aiconfig-variations`, `aiconfig-tools`, `aiconfig-projects`, `aiconfig-online-evals`, `aiconfig-targeting`
- **Metrics** (`skills/metrics/`) — `launchdarkly-metric-choose`, `launchdarkly-metric-create`, `launchdarkly-metric-instrument`
- **Onboarding** (`skills/onboarding/`) — `onboarding` plus nested `mcp-configure`, `sdk-install`, `first-flag`

> **Note on `aiconfig-projects`:** the skill name is misleading. LaunchDarkly has one concept called "project" — it holds feature flags, AI Configs, segments, and metrics together. There is no separate "AI Config project" type. This skill just creates a regular LD project, framed from an AI-workflow entry point.

**If you can't install skills at all, you're not blocked.** The LaunchDarkly MCP server exposes the same actions as raw tools (`mcp__LaunchDarkly__create-ai-config`, `mcp__LaunchDarkly__create-feature-flag`, etc.). Skills are playbook overlays on top of those tools; the tools alone are enough to run the demo. You can also do everything in this runbook in the LaunchDarkly web UI.

Verify a skill install by tab-completing `/launchdarkly:` in Claude Code, or check `.claude/skills/` for the symlinks.

### 3. Configure the LaunchDarkly MCP server

Run the onboarding skill — it walks you through authenticating with your LaunchDarkly account and registering the MCP server with Claude Desktop / Claude Code:

```
/onboarding/mcp-configure
```

Restart Claude when prompted. After restart, MCP tools like `mcp__launchdarkly__create_flag` should appear.

> **Manual path (if the skill doesn't wire it up):** edit `~/Library/Application Support/Claude/claude_desktop_config.json` and add an `mcpServers.LaunchDarkly` entry that runs `npx -y --package @launchdarkly/mcp-server -- mcp start --api-key <your-ld-api-token>`. Keep `preferences` and `mcpServers` as sibling keys inside a single outer `{}`. Fully quit and relaunch Claude after saving.

### 4. Create a LaunchDarkly project for the demo

Create a standard LaunchDarkly project. There is no distinct "AI Config project" type — a single LD project holds your feature flags, AI Configs, segments, and metrics together.

**UI path:** LaunchDarkly → Projects → New project.

- Project name: `decor-agent-demo`
- Environments: `production`

Copy the **server-side SDK key** for `production` from the environment detail page; you'll paste it in step 6.

**Alternative — skill:** `/aiconfig-projects` walks you through the same flow and calls the MCP tool for you. The skill name is slightly misleading (it creates an ordinary project, not an AI-specific one), but it's convenient.

### 5. Write `app/flags.py` and `app/llm.py`

These are the Python glue that connects the agent to LaunchDarkly. This is the main code-side work for the demo. See [Appendix D — `app/flags.py` + `app/llm.py` skeleton](#appendix-d--appflagspy--appllmpy-skeleton) for the reference implementation.

Key behaviors:

- `flags.init_client()` runs on server startup. If `LD_SDK_KEY` is empty, it logs a warning and stays in **offline mode** — the app falls back to the prompts in `app/prompts.py` and the default model from `app/config.py`. This is how local dev stays fast and free.
- `flags.get_completion_config(key, context, default)` returns a `ResolvedAIConfig` wrapping the LD SDK's output. In offline mode it builds the resolved config from the default. Either way, tools and the agent node just read `.model`, `.system_prompt`, `.max_tokens`, `.temperature`, and call `.track_success(...)` / `.track_tokens(...)` without caring where the values came from.
- `llm.get_llm(model, max_tokens, temperature)` is an `@lru_cache`'d `ChatAnthropic` factory. Every tool and the agent node go through this; no more inline `ChatAnthropic(...)` instantiation.

### 6. Set environment variables

Edit `decor-agent/.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
LD_SDK_KEY=sdk-server-...
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### 7. Refactor tools + agent node

Every tool (`app/tools/style_advisor.py`, `room_planner.py`, `trend_spotter.py`) and the agent node (`app/nodes/agent.py`) must switch from hardcoded prompts/models to:

```python
from app.flags import build_context, get_completion_config, AIConfigDefault, current_context_key
from app.llm import get_llm
from app.prompts import STYLE_ADVISOR_PROMPT  # fallback

context = build_context(current_context_key())
default = AIConfigDefault(
    model=settings.default_model,
    system_prompt=STYLE_ADVISOR_PROMPT,
    max_tokens=settings.max_tokens,
)
cfg = get_completion_config("decor-style-advisor", context, default)
llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature)
# ... invoke, then cfg.track_success(), cfg.track_tokens(usage)
```

Run `python test_agent.py` in offline mode (no `LD_SDK_KEY`). **All 13 tests must still pass** — this proves the refactor didn't regress routing.

### 8. Create a seed `generate_traffic.py`

See [Phase 7](#phase-7--generate-traffic--dashboard-5-min). This is the load generator that populates your monitoring dashboard.

### 9. Rehearse end-to-end

Run every phase at least twice before demo day. Cache your LLM calls during rehearsal (set a lower-volume test model like Haiku for dry runs) — a clean $2 rehearsal is better than a flaky $40 one.

---

## Phase 0 — Baseline (2 min)

Before any LaunchDarkly integration is discussed, show the agent working.

### Demo beats

1. Open `http://localhost:8000/` (the web UI) in the browser.
2. Type: "What paint color works with walnut floors?"
3. Point at the structured response — specific products, opinionated tone.
4. Open dev tools, point at the `/api/chat` response payload — highlight `metadata.routed_to: "style_advisor"` and the token counts.
5. Narrate: *"This is what ships today. Works great. Now let's talk about what happens when we want to change it."*

**Do not mention LaunchDarkly yet.** The whole phase establishes what "before" looks like.

---

## Phase 1 — Kill-switch flag (5 min)

Establish the simplest LaunchDarkly primitive: a boolean flag that gates traffic.

### What you create

| Artifact | Value |
|---|---|
| Flag key | `decor-agent-enabled` |
| Flag type | Boolean |
| Default serve (production) | `true` |
| Fallback value in code | `true` |

### Steps

**1. Create the flag via agent skill:**

In Claude Code, invoke:

```
/launchdarkly-flag-create
```

Tell the skill:
- Flag key: `decor-agent-enabled`
- Type: boolean
- Description: "Kill switch for the decor agent chat endpoint"
- Default: on

The skill generates the LD-side flag and suggests a code patch for `server.py`. Accept the code patch or merge it manually:

```python
# server.py — inside the /api/chat handler, before run_agent()
from app.flags import get_flag, build_context

context = build_context(context_key)
if not get_flag("decor-agent-enabled", context, default=True):
    return JSONResponse(
        status_code=200,
        content={
            "response": "Decor Agent is temporarily unavailable for maintenance. Check back soon!",
            "metadata": {"routed_to": "maintenance"},
            "message_id": message_id,
            "timestamp": timestamp,
        },
    )
```

**2. Verify the flag exists:**

```
/launchdarkly-flag-discovery
```

Look for `decor-agent-enabled` in the output.

### Demo beats

1. Type a question in the UI — normal response.
2. Switch to the LD UI, toggle `decor-agent-enabled` **off**, save.
3. Send another question — maintenance message returns.
4. Toggle back on — normal response resumes.

**The line to land:** *"You just saw a production service behavior change with zero redeploys. That's the baseline. Everything else we build today is that same pattern, but for model, prompts, and rollout strategy."*

---

## Phase 2 — Lift prompts into AI Configs (8 min)

Move the four prompts (main agent + 3 specialists) out of `app/prompts.py` and into LaunchDarkly AI Configs so they can be edited at runtime.

### What you create

| AI Config key | Purpose | Initial variation name | Initial model |
|---|---|---|---|
| `decor-agent-main` | Orchestrator/router | `v1-baseline` | `claude-sonnet-4-20250514` |
| `decor-style-advisor` | Style specialist tool | `v1-baseline` | `claude-sonnet-4-20250514` |
| `decor-room-planner` | Room planner specialist tool | `v1-baseline` | `claude-sonnet-4-20250514` |
| `decor-trend-spotter` | Trend specialist tool | `v1-baseline` | `claude-sonnet-4-20250514` |

For each config, the initial variation's system prompt is a verbatim copy of the current prompt from `app/prompts.py`.

> **Model naming:** `claude-sonnet-4-20250514` is a dated Sonnet 4 snapshot. As of April 2026 the current Claude 4.X family includes **Sonnet 4.6** (`claude-sonnet-4-6`) and **Opus 4.7** (`claude-opus-4-7`). The pinned snapshot above is fine for demo stability (it won't shift under you mid-demo), but consider upgrading before a real production rollout.

### Steps

**1. Confirm the LaunchDarkly project exists:**

All four AI Configs live inside the `decor-agent-demo` project you created in pre-demo step 4. No separate grouping is needed — AI Configs, flags, and metrics all sit together in one project.

If you skipped that step, create it now via UI (Projects → New project) or via the skill `/aiconfig-projects`.

**2. Create each AI Config:**

Run four times, once per config:

```
/aiconfig-create
```

For `decor-agent-main`:
- Config key: `decor-agent-main`
- Type: agent (or completion — completion is simpler for this demo, pick completion)
- Initial variation name: `v1-baseline`
- Model: `claude-sonnet-4-20250514`
- `max_tokens`: 1024
- `temperature`: 1.0
- System prompt: paste the current `AGENT_SYSTEM_PROMPT` from `app/prompts.py`

Repeat for `decor-style-advisor`, `decor-room-planner`, `decor-trend-spotter` with their respective prompts.

**3. Refactor the Python code:**

Already done in pre-demo setup step 7. Re-verify: tests should still pass in offline mode, and when the server boots with `LD_SDK_KEY` set, logs should show `launchdarkly.initialized` and each request should log `ai_config.fetched config_key=... source=launchdarkly`.

**4. Verify a live fetch:**

Start the server with `LD_SDK_KEY` set. Send a test request. In the logs, confirm:

```
ai_config.fetched config_key=decor-agent-main source=launchdarkly variation=v1-baseline
ai_config.fetched config_key=decor-style-advisor source=launchdarkly variation=v1-baseline
```

### Demo beats

1. Send a style question. Normal response.
2. Open `decor-style-advisor` in the LD UI. Edit the `v1-baseline` system prompt — add the line: *"Prefer IKEA and Article over designer brands."*
3. Save the variation.
4. Send the same style question again. Response now recommends IKEA/Article pieces. **No redeploy.**

**The line to land:** *"The prompt is now configuration, not code. Product, design, or an applied researcher can change agent behavior without filing a PR."*

---

## Phase 3 — Variations + targeting (6 min)

This is the headline phase. Two personalities, same question, different answers — targeted by user segment.

### What you create

On `decor-agent-main`, add two new variations alongside `v1-baseline`:

| Variation | Prompt emphasis | Target segment |
|---|---|---|
| `budget-conscious` | IKEA, Target, Article, thrift, DIY, name price tiers, flag splurges | `user-tier == "free"` |
| `luxury-curator` | Design Within Reach, designer fabrics, unlacquered brass, custom millwork | `user-tier == "premium"` |

For the tool configs (`decor-style-advisor`, etc.), optionally add matching budget/luxury variations. For the demo's headline moment, only `decor-agent-main` needs both variations — the specialist tools can stay on `v1-baseline`.

**Model swap (optional, strong):** set `decor-style-advisor` to use `claude-haiku-4-5-20251001` in its default variation. Creative style questions are forgiving of cheaper models. Leave `decor-room-planner` on Sonnet (needs reasoning about dimensions).

### Steps

**1. Add variations:**

```
/aiconfig-variations
```

For `decor-agent-main`, create two variations. See [Appendix A](#appendix-a--writing-variation-prompts) for the full prompt text of each.

**2. Set targeting rules:**

```
/launchdarkly-flag-targeting
```

Or edit targeting in the LD UI directly for the `decor-agent-main` AI Config:

```
IF user-tier IS "premium"    → serve luxury-curator
IF user-tier IS "free"       → serve budget-conscious
DEFAULT                      → serve budget-conscious
```

**3. Update the server to stamp `user-tier` on the context:**

In `server.py`, enrich the context with `user-tier` (for the demo, read it from a request header or the `context_key` prefix):

```python
# In build_context()
tier = "premium" if context_key.startswith("premium-") else "free"
builder.set("user-tier", tier)
```

For the demo, you'll just use context keys like `premium-alice` and `free-bob` to switch personas on the fly.

**4. (Optional) Swap models on specialist tools:**

In `decor-style-advisor`, edit `v1-baseline` to use `claude-haiku-4-5-20251001`. Save.

### Demo beats

**Beat 1 — same question, two answers:**

1. Type: *"Help me pick a sofa for my living room, budget-friendly but stylish"* with context_key set to `free-alice` (via a header or UI dropdown — pre-wire this in the web UI).
2. Response recommends Article, IKEA, or Wayfair options with price tiers.
3. Change the context dropdown to `premium-alice`. Same question.
4. Response recommends Design Within Reach, custom upholstery, possibly a named designer.

**Beat 2 — model swap visibility:**

1. Point at the response latency — style questions are noticeably faster now (Haiku).
2. Point at the metadata: `model: "claude-haiku-4-5-20251001"`.
3. Narrate: *"Room planning still uses Sonnet because it needs reasoning. Style advice uses Haiku because creative work is forgiving. Same agent, right-sized models per task."*

**The line to land:** *"Same code path. Same user message. Two genuinely different — and both valid — answers. And we pay Haiku rates on half the traffic."*

---

## Phase 4 — Offline evals (5 min)

Prove a variation is safe to ship before it touches real users. Runs a labeled test dataset against each variation, scores every row with criteria (factuality, relevance, etc.), and produces a side-by-side scorecard — all hosted inside LaunchDarkly.

> **Product surface:** Offline evaluations live in the LaunchDarkly **LLM playground** (**Project → AI → Playground** in the UI; docs call it "LLM playground"). Online evaluators (Phase 6) score real production traffic; offline evaluations score a fixed dataset *before* rollout. There is no dedicated agent skill yet — the flow below is UI-driven. (If you want a CI-gated check in addition, keep the local `evals/run_offline.py` harness as a supplement — see "Optional local harness" at the end of this phase.)

### What you create

1. A **dataset** (CSV or JSONL) with labeled design questions.
2. An **evaluation** in the Playground that runs your dataset against two or more variations of `decor-agent-main`.
3. A set of **criteria** (factuality, relevance, on-brand tone) that score each row.

### Dataset format

LD offline datasets accept these fields per row:

| Field | Required | Purpose |
|---|---|---|
| `input` | yes | The prompt sent to the variation. String or JSON object. |
| `expected_output` | optional | Ideal answer, used for comparison-style criteria. |
| `variables` | optional | Values for `{{placeholder}}` slots in prompt templates. |
| `metadata` | optional | Arbitrary JSON for filtering/reporting (e.g. `{"category": "budget"}`). |

Save as `evals/decor_dataset.jsonl`:

```jsonl
{"input": "I want mid-century modern on a $1500 budget", "metadata": {"category": "budget", "style": "mid-century"}}
{"input": "Make my space feel maximalist and colorful", "metadata": {"category": "style", "fail_if_contains": ["minimalist", "monochromatic"]}}
{"input": "My studio is 200 sqft. Recommend a sectional.", "expected_output": "apartment sofa or loveseat under 72 inches", "metadata": {"category": "accuracy"}}
{"input": "I have an 8x10 bedroom. Does a king bed fit?", "expected_output": "no — a queen is the largest practical choice", "metadata": {"category": "accuracy"}}
{"input": "Tight budget, under $500 total", "metadata": {"category": "budget", "cap_usd": 500}}
{"input": "Splurge encouraged, quality over price", "metadata": {"category": "luxury", "floor_usd": 1000}}
```

Aim for 20–30 rows spread across the style/budget/accuracy/trend buckets.

### Steps

**1. Create the evaluation in the LLM playground.**

- LaunchDarkly → **AI → Playground** → **New evaluation**.
- The **Input** tab opens. Upload `evals/decor_dataset.jsonl`. LD validates the format and detects the schema. (CSV is also accepted.)

**2. Pick variations to compare.**

- Point the evaluation at `decor-agent-main`.
- Select both variations: `budget-conscious` and `luxury-curator`.
- Each row in the dataset will run through every selected variation.

**3. Attach criteria.**

One criterion = one measurement per row (returns a 0–1 score with reasoning). Add at minimum:

- **Factuality** — does the response contain real products / real dimensions / real clearances?
- **Relevance** — does the response address the asked question without topic drift?
- **Budget adherence** — does the response respect `metadata.cap_usd` / `metadata.floor_usd` when present?

Use LD's built-in criteria where they fit; author a custom LLM-as-judge criterion for budget adherence (the prompt can reference `{{metadata.cap_usd}}`).

**4. Run it.**

Click **Run evaluation**. LD executes every (row × variation) combination, calls each criterion, and writes a scorecard.

**5. Read the scorecard.**

The UI surfaces:

- **Status counts** — how many rows passed/failed per variation.
- **Aggregate scores per criterion** — e.g. "budget-adherence: budget-conscious 0.92, luxury-curator 0.41".
- **Latency + token usage** — per variation, for cost/performance framing.
- **Row-level outputs** — click a row to see the response plus each criterion's score and reasoning.

Export results as CSV/JSONL if you want to archive them alongside the release.

### Optional local harness

If you want a CI-gated version (runs on every PR, blocks merge on regression), keep a thin Python script that loads the same `evals/decor_dataset.jsonl`, calls `run_agent(message, context_key=f"eval-{tier}-{id}")` once per variation, and scores predicate-style rules (`metadata.cap_usd`, `metadata.fail_if_contains`) locally. Two benefits: (a) it runs without LD network access, (b) you can gate merges on it. The LD Playground run stays the authoritative release gate; the local harness is for fast iteration loops.

### Expected result

`luxury-curator` should score low on budget-constrained rows — that's the evidence the targeting rule makes sense. `budget-conscious` should underperform on splurge rows.

### Demo beats

1. In the Playground, click into the already-run evaluation (pre-run it before the demo so you're not watching a progress bar live).
2. Land on the aggregate scorecard — highlight the gap: `budget-adherence: budget-conscious 0.92 vs luxury-curator 0.41`.
3. Click into one failing row for `luxury-curator` — show the LLM-as-judge reasoning explaining *why* the response blew the budget.
4. Narrate: *"If we shipped luxury-curator to everyone, our free users would get responses that miss their constraints. That's exactly the regression the Playground caught before a single prod user saw it."*

**The line to land:** *"Offline evals catch the predictable failures before release. Online evals catch the drift after. Together they're the guardrails."*

---

## Phase 5 — Guarded rollout (6 min)

Ramp a new variation from 10% to 100% of traffic with automatic rollback if quality or operational metrics breach.

### What you create

| Metric | Metric type | Analysis method | Threshold |
|---|---|---|---|
| `chat.error_rate` | Custom conversion binary (occurred / did not occur) | Proportion of events | < 0.02 (2%) |
| `chat.p95_latency_ms` | Custom numeric | Percentile (p95) | < 8000 (8 seconds) |
| `chat.fallback_response_rate` | Custom conversion binary | Proportion of events | < 0.01 (1%) |

> LD metric **types** are: Custom conversion binary, Custom conversion count, Custom numeric, Clicked/tapped, Page viewed. "Proportion" and "percentile" are **analysis methods** you pick when viewing a numeric metric, not types. Configure the type first, then choose how to analyze it.

A guarded rollout plan on `decor-agent-main`:

```
Stage 1: 10% budget-conscious-v2 / 90% budget-conscious-v1   (30 min)
Stage 2: 25% / 75%                                            (30 min)
Stage 3: 50% / 50%                                            (60 min)
Stage 4: 100%
```

Auto-rollback if any metric breaches threshold.

### Steps

**1. Create metrics:**

```
/launchdarkly-metric-choose
```

Ask the skill: "I need metrics for a production LLM agent. I track error rate, latency p95, and fallback response rate."

Then:

```
/launchdarkly-metric-create
```

For each metric, wire the event source. The metrics feed off the structured logs you already emit — you'll need a thin shim that converts `chat.error` log events into LaunchDarkly `track()` calls. Pattern:

```python
# In server.py /api/chat handler
from app.flags import get_client

ld = get_client()
if ld is not None:
    ld.track("chat_error", context, value=1)
    ld.track("chat_latency_ms", context, value=duration_ms)
```

**2. Create a `budget-conscious-v2` variation:**

Use `/aiconfig-variations` to clone `budget-conscious` and tweak the prompt — add a new line like *"When recommending products, include approximate cost in USD alongside each named item."*

**3. Configure the guarded rollout:**

Guarded rollouts are configured in the **LD UI** (on the AI Config's targeting / release tab) or via the release-specific MCP tools — there is no dedicated "guarded rollout" skill. The `/launchdarkly-flag-targeting` skill covers *regular* targeting rules but does not specifically own guarded-rollout mechanics.

In the LD UI, start a guarded rollout on the `budget-conscious` → `budget-conscious-v2` transition for free-tier users. Ramp schedule as above, auto-rollback wired to the three metrics.

**4. (Demo prep) Break one variation on purpose:**

Create `budget-conscious-broken` that returns an empty string or uses a prompt that consistently produces malformed output. This is your planted failure for the demo.

### Demo beats

1. Open the LD UI guarded rollout panel. Point at the ramp schedule.
2. Launch `generate_traffic.py` at full blast. Show metrics accruing in real time.
3. Quickly swap the `v2` variation to `budget-conscious-broken` mid-ramp.
4. Watch latency/error metrics spike in the monitoring dashboard.
5. LaunchDarkly auto-reverts. Point at the rollback event in the timeline.

**The line to land:** *"You don't need an on-call engineer watching graphs. The system reverts itself when quality breaks. That's ship-it-safely without ship-it-scared."*

---

## Phase 6 — Online evals + LLM judges (6 min)

Score every real response in production with an LLM-as-judge. Catches drift that offline evals can't — especially **trend staleness**, which is why we have a `trend_spotter` tool in the first place.

### What you create

Three judges attached to the relevant AI Configs:

| Judge | Attached to | Question | Scale |
|---|---|---|---|
| `is_opinionated` | `decor-agent-main` | "Does this response commit to a concrete recommendation, or does it hedge?" | 0-1 |
| `names_specifics` | `decor-agent-main` | "Does this response name specific products, colors, or dimensions?" | 0-1 |
| `trend_still_current` | `decor-trend-spotter` | "Given today's date is {current_date}, are the trend claims in this response still current? Flag any trends that are > 3 years stale or that have reversed." | 0-1 |

### Steps

**1. Attach judges:**

```
/aiconfig-online-evals
```

For each judge:
- Give it a system prompt defining the scoring rubric
- Set sampling rate (start with 100% for the demo so every request gets scored; in production you'd sample 10-25% to control cost)
- Set the model for the judge itself (Haiku is fine — judges don't need Sonnet)

**2. Verify judge output:**

Send a request, then check the LD monitoring dashboard for the judge score alongside the response.

### Demo beats

**The trend-drift moment:**

1. Show a `trend_spotter` response from 6 months ago (you'll need to have run it and captured the output — keep a screenshot or re-create by temporarily backdating the judge's `current_date` variable).
2. Point at the judge score: `trend_still_current: 0.9`.
3. Now send the same question live. Point at today's judge score: `trend_still_current: 0.4`.
4. Narrate: *"Same prompt. Same model. The world changed. Offline evals can't catch this — they'd pass today and still pass a year from now. Online evals flag the decay in real time."*

**The opinionated judge:**

1. Send a new request, see the `is_opinionated` score.
2. If you want to be dramatic, temporarily revert one of the system prompts to remove the "Never say 'it depends'" constraint. Watch the judge score drop.

**The line to land:** *"Offline evals protect you from known failure modes. Online evals protect you from unknown ones."*

---

## Phase 7 — Generate traffic + dashboard (5 min)

The payoff phase. All the prior work shows up as curves on one dashboard.

### What you create

A load generator at `decor-agent/generate_traffic.py`. Skeleton:

```python
# generate_traffic.py
import asyncio, random, uuid, httpx

SEED_MESSAGES = [
    "What paint color works with dark oak floors?",
    "I have a 12x14 living room and $2000 budget",
    "Is terrazzo still trending?",
    "Should I go velvet or linen for my sofa?",
    "How do I make a small bathroom feel bigger?",
    "My bedroom is 10x11 and I need a queen bed plus WFH desk",
    "What's replacing the all-white kitchen?",
    "Help me compromise between mid-century modern and farmhouse",
    "I want a boho vibe but also need to fit a 90-inch sectional in a 10x12 room",
    "Best color for a north-facing room with little natural light?",
    # ... 10-20 more
]

PERSONAS = [
    ("free-", 0.7),      # 70% of traffic is free-tier
    ("premium-", 0.3),   # 30% premium
]

async def fire_one(client: httpx.AsyncClient):
    msg = random.choice(SEED_MESSAGES)
    prefix = random.choices([p[0] for p in PERSONAS], weights=[p[1] for p in PERSONAS])[0]
    context_key = f"{prefix}{uuid.uuid4().hex[:8]}"
    await client.post(
        "http://localhost:8000/api/chat",
        json={"message": msg, "context_key": context_key},
        timeout=60,
    )

async def main(total: int = 200, concurrency: int = 4):
    async with httpx.AsyncClient() as client:
        sem = asyncio.Semaphore(concurrency)
        async def bounded():
            async with sem:
                await fire_one(client)
        await asyncio.gather(*[bounded() for _ in range(total)])

if __name__ == "__main__":
    import sys
    total = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    asyncio.run(main(total=total))
```

### Steps

**1. Pre-demo: seed overnight data**

Run 24 hours before the demo:

```bash
python generate_traffic.py 1000
```

This gives your dashboard a realistic backdrop of real requests against real variations before you step on stage.

**2. Demo-time: fire a live burst**

```bash
python generate_traffic.py 50
```

Does 50 requests at concurrency 4, finishes in ~2 minutes.

### Demo beats — dashboard walkthrough

Order matters. Each chart builds on the last.

1. **Request volume split by variation** — shows targeting is working as configured. Should see the 70/30 free/premium split.
2. **Cost per variation (USD or tokens)** — luxury-curator costs ~3× more per request. Acceptable because it's 30% of traffic and premium-tier.
3. **Model cost per tool** — style_advisor on Haiku at ~$0.005/request, room_planner on Sonnet at ~$0.02/request. Same agent, right-sized.
4. **Latency p50 / p95 by variation** — style questions are faster now. Room planning is slower but higher quality.
5. **Judge scores over time** — `is_opinionated` and `names_specifics` flat and healthy. `trend_still_current` drifting downward (the online eval story from Phase 6).
6. **Guarded rollout timeline** — the auto-revert event from Phase 5 shows up as a visible spike-then-recovery.

### The closing line

> *"Every change we just shipped — prompt edits, variations, model swaps, rollouts, rollbacks — happened without a single redeploy. One loop: ship, observe, iterate, reship. That's the LaunchDarkly AI iteration loop."*

---

## Appendix A — Writing variation prompts

The variations are the demo's personality. Quality matters. Use these as starting points and polish.

### `budget-conscious` variation (for `decor-agent-main`)

Append to the existing `AGENT_SYSTEM_PROMPT`:

```
## Budget Conscious Mode

The user is budget-conscious. When recommending products or materials:
- Lead with accessible brands: IKEA, Target, Wayfair, Article, World Market, Urban Outfitters.
- Include approximate prices in USD for each named item.
- When naming a high-end piece, offer an accessible alternative immediately ("Design Within Reach × or IKEA Ektorp").
- Mention DIY, thrift, or secondhand options when genuinely viable (Facebook Marketplace, Craigslist, estate sales).
- Flag splurges explicitly: "if you can stretch the budget, [premium option] is worth it because X."
- Respect tight budgets. Under $500 total means under $500 total — don't recommend a single $400 sofa.
```

### `luxury-curator` variation (for `decor-agent-main`)

Append to the existing `AGENT_SYSTEM_PROMPT`:

```
## Luxury Curator Mode

The user values quality, craftsmanship, and distinction. When recommending:
- Lead with designer and trade brands: Design Within Reach, B&B Italia, Pinch London, Knoll, Roman & Williams, Lawson-Fenning, Nickey Kehoe.
- Name specific designers when relevant ("a Pierre Jeanneret-inspired teak lounge chair").
- Specify materials precisely: "hand-rubbed unlacquered brass," "mohair velvet," "travertine with honed finish," "solid white oak, rift-sawn."
- Include approximate prices — premium is expected, but the user still wants transparency.
- Suggest custom or made-to-order pieces when appropriate.
- Skip mass-market references entirely. IKEA does not appear in this mode.
```

### When to add a variation versus a new config

- **New variation** — same role, different personality, tone, or model. Examples: budget vs. luxury, Sonnet vs. Haiku, concise vs. detailed.
- **New AI Config** — genuinely new capability. Example: a new `decor-lighting-expert` tool would be a new config, not a variation.

Rule of thumb: if the question "which one is correct?" has different answers for different users, it's a variation. If the question is "which one applies to this request?", it's a new config.

---

## Appendix B — Targeting context attributes

The context you build for LaunchDarkly determines which variation fires. At minimum, include:

| Attribute | Example values | Purpose |
|---|---|---|
| `key` (context key) | `user-42`, `premium-alice`, `anon-abc123` | Identity for bucketing |
| `user-tier` | `free`, `premium`, `enterprise` | Phase 3 targeting |
| `session-id` | uuid | For session-level consistency |
| `app-version` | `1.0.0` | For version-gated rollouts |
| `locale` | `en-US`, `en-GB` | For region-aware variations later |

When adding targeting rules, use the dedicated context attributes, never the raw context key. `user-tier == "premium"` is clear; `key starts with "premium-"` is brittle.

> **Naming convention:** this runbook uses kebab-case attribute names (`user-tier`, `session-id`, `app-version`) because they read well in prose. LaunchDarkly's documented convention across SDKs — especially JS/React — is **camelCase** (`userTier`, `sessionId`, `appVersion`). Both work, but pick one and stay consistent across your agent code, targeting rules, and dashboards. If you later add a web client that also sends contexts, camelCase will save you a migration.

---

## Appendix C — Pre-demo checklist

Run this the morning of the demo.

- [ ] `decor-agent-demo` LaunchDarkly project exists, production env configured
- [ ] `LD_SDK_KEY` set in `.env`, server-side key from production env
- [ ] Both Python SDKs installed (`pip list | grep launchdarkly` shows both)
- [ ] All four AI Configs exist: `decor-agent-main`, `decor-style-advisor`, `decor-room-planner`, `decor-trend-spotter`
- [ ] Each AI Config has a `v1-baseline` variation with a working prompt
- [ ] `decor-agent-main` has `budget-conscious` and `luxury-curator` variations
- [ ] Targeting rules on `decor-agent-main` map `user-tier` to the right variations
- [ ] `decor-style-advisor` default variation uses Haiku (if doing the model-swap beat)
- [ ] `is_opinionated`, `names_specifics`, `trend_still_current` judges attached
- [ ] `chat.error_rate`, `chat.p95_latency_ms`, `chat.fallback_response_rate` metrics exist
- [ ] Overnight traffic ran — dashboard has ≥500 prior requests
- [ ] `budget-conscious-broken` variation exists as the planted failure for Phase 5
- [ ] `evals/decor_dataset.jsonl` populated with ≥20 labeled rows (`input` + `metadata`)
- [ ] Offline evaluation in **AI → Playground** is pre-run against `budget-conscious` + `luxury-curator` — scorecard loads in one click
- [ ] (Optional) local `evals/run_offline.py` harness runs cleanly as a CI supplement
- [ ] `python test_agent.py` passes 13/13 with `LD_SDK_KEY` set AND with it unset
- [ ] Server starts cleanly with `python server.py`, logs show `launchdarkly.initialized`
- [ ] Web UI at `http://localhost:8000/` works and has a context-key/tier dropdown for Phase 3
- [ ] Backup: a recorded screencast of the full demo in case live fails

---

## Appendix D — `app/flags.py` + `app/llm.py` skeleton

Reference implementation for the code side of the demo. **Do not write these files until you've installed the SDKs and created at least one AI Config** — otherwise you'll be debugging blind.

### `app/llm.py`

```python
from functools import lru_cache
from langchain_anthropic import ChatAnthropic
from app.config import get_settings


@lru_cache(maxsize=32)
def get_llm(model: str, max_tokens: int = 1024, temperature: float = 1.0) -> ChatAnthropic:
    return ChatAnthropic(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=get_settings().anthropic_api_key,
    )
```

### `app/flags.py`

```python
from __future__ import annotations
import contextvars
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

_ld_client = None
_ai_client = None

_current_ctx_key: contextvars.ContextVar[str] = contextvars.ContextVar(
    "decor_current_ctx_key", default="anonymous"
)


def set_current_context_key(key: str) -> None:
    _current_ctx_key.set(key)


def current_context_key() -> str:
    return _current_ctx_key.get()


@dataclass(frozen=True)
class AIConfigDefault:
    """Fallback values used when LD is offline or the config is missing."""
    model: str
    system_prompt: str
    max_tokens: int = 1024
    temperature: float = 1.0


@dataclass
class ResolvedAIConfig:
    """What tools and nodes read. Wraps the LD tracker so callers are vendor-neutral."""
    model: str
    system_prompt: str
    max_tokens: int
    temperature: float
    source: str                # "launchdarkly" | "fallback" | "fallback_error"
    variation: Optional[str] = None
    config_key: Optional[str] = None
    _tracker: Any = None

    def track_success(self) -> None:
        if self._tracker is not None:
            try: self._tracker.track_success()
            except Exception as e: log.warning("tracker.error", op="success", error=str(e))

    def track_error(self) -> None:
        if self._tracker is not None:
            try: self._tracker.track_error()
            except Exception as e: log.warning("tracker.error", op="error", error=str(e))

    def track_tokens(self, input_tokens: int, output_tokens: int) -> None:
        if self._tracker is not None:
            try:
                from ldai.tracker import TokenUsage  # ldai.tracker, not ldai.client (SDK >=0.17.0)
                self._tracker.track_tokens(TokenUsage(
                    input=input_tokens, output=output_tokens, total=input_tokens + output_tokens,
                ))
            except Exception as e:
                log.warning("tracker.error", op="tokens", error=str(e))

    def track_duration(self, duration_ms: int) -> None:
        if self._tracker is not None:
            try: self._tracker.track_duration(duration_ms)
            except Exception as e: log.warning("tracker.error", op="duration", error=str(e))


def init_client() -> None:
    global _ld_client, _ai_client
    settings = get_settings()
    if not settings.ld_sdk_key:
        log.warning("launchdarkly.offline_mode", reason="LD_SDK_KEY not set")
        return
    try:
        import ldclient
        from ldclient.config import Config as LDClientConfig
        from ldai.client import LDAIClient
    except ImportError as e:
        log.error("launchdarkly.sdk_not_installed", error=str(e))
        return
    try:
        ldclient.set_config(LDClientConfig(settings.ld_sdk_key))
        _ld_client = ldclient.get()
        _ai_client = LDAIClient(_ld_client)
        log.info("launchdarkly.initialized")
    except Exception as e:
        log.error("launchdarkly.init_failed", error=str(e))


def close_client() -> None:
    global _ld_client, _ai_client
    if _ld_client is not None:
        try: _ld_client.close()
        except Exception as e: log.warning("launchdarkly.close_error", error=str(e))
    _ld_client = None
    _ai_client = None


def get_client():
    return _ld_client


def build_context(context_key: str, **attrs):
    """Build an LD Context, or a dict-like stand-in for offline mode."""
    if _ai_client is None:
        return {"key": context_key, **attrs}
    from ldclient import Context
    builder = Context.builder(context_key).kind("user")
    # Default attribute: user-tier inferred from key prefix (for demo convenience)
    if "user-tier" not in attrs:
        if context_key.startswith("premium-"): attrs["user-tier"] = "premium"
        elif context_key.startswith("free-"): attrs["user-tier"] = "free"
        else: attrs["user-tier"] = "free"
    for k, v in attrs.items():
        builder.set(k, v)
    return builder.build()


def get_flag(key: str, context, default: bool = False) -> bool:
    if _ld_client is None:
        return default
    try:
        return _ld_client.variation(key, context, default)
    except Exception as e:
        log.error("flag.error", key=key, error=str(e))
        return default


def get_completion_config(
    config_key: str,
    context,
    default: AIConfigDefault,
) -> ResolvedAIConfig:
    if _ai_client is None:
        log.debug("ai_config.offline", config_key=config_key)
        return ResolvedAIConfig(
            model=default.model,
            system_prompt=default.system_prompt,
            max_tokens=default.max_tokens,
            temperature=default.temperature,
            source="fallback",
            config_key=config_key,
        )
    try:
        from ldai.client import AICompletionConfigDefault, ModelConfig, LDMessage
        ld_default = AICompletionConfigDefault(
            enabled=True,
            model=ModelConfig(
                name=default.model,
                parameters={
                    "max_tokens": default.max_tokens,
                    "temperature": default.temperature,
                },
            ),
            messages=[LDMessage(role="system", content=default.system_prompt)],
        )
        cfg = _ai_client.completion_config(config_key, context, ld_default)

        system_prompt = default.system_prompt
        for msg in cfg.messages or []:
            if msg.role == "system":
                system_prompt = msg.content
                break

        # Guard: cfg.model is None when the serving variation has no model set.
        # Fall back to the default model, but keep the LD-supplied system prompt.
        if cfg.model is None:
            model_name = default.model
            max_tokens = default.max_tokens
            temperature = default.temperature
            log.warning("ai_config.model_missing", config_key=config_key)
        else:
            model_name = cfg.model.name
            max_tokens = cfg.model.get_parameter("max_tokens") or default.max_tokens
            temperature = cfg.model.get_parameter("temperature")
            if temperature is None: temperature = default.temperature

        log.info(
            "ai_config.fetched",
            config_key=config_key,
            source="launchdarkly",
            model=model_name,
        )
        return ResolvedAIConfig(
            model=model_name,
            system_prompt=system_prompt,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            source="launchdarkly",
            config_key=config_key,
            _tracker=cfg.tracker,
        )
    except Exception as e:
        log.error("ai_config.fetch_failed", config_key=config_key, error=str(e))
        return ResolvedAIConfig(
            model=default.model,
            system_prompt=default.system_prompt,
            max_tokens=default.max_tokens,
            temperature=default.temperature,
            source="fallback_error",
            config_key=config_key,
        )
```

### Example refactored tool (`app/tools/style_advisor.py`)

```python
import time
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import ToolException, tool

from app.config import get_settings
from app.flags import AIConfigDefault, build_context, current_context_key, get_completion_config
from app.llm import get_llm
from app.logging import get_logger
from app.prompts import STYLE_ADVISOR_PROMPT

log = get_logger(__name__)


@tool("style_advisor")
def style_advisor(question: str, style_preferences: str = "not specified") -> str:
    """Get interior design style advice. Use this for questions about design styles, color palettes, material choices, furniture pairing, aesthetic direction, or 'should I go with X or Y' style comparisons."""
    settings = get_settings()

    context = build_context(current_context_key())
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=STYLE_ADVISOR_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-style-advisor", context, default)

    user_content = question
    if style_preferences and style_preferences != "not specified":
        user_content = f"Style preferences: {style_preferences}\n\nQuestion: {question}"

    log.info("tool.invoke", tool="style_advisor", model=cfg.model, variation=cfg.variation)
    llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature)

    start = time.perf_counter()
    try:
        response = llm.invoke([
            SystemMessage(content=cfg.system_prompt),
            HumanMessage(content=user_content),
        ])
        latency_ms = int((time.perf_counter() - start) * 1000)

        usage = getattr(response, "usage_metadata", None) or {}
        cfg.track_success()
        cfg.track_duration(latency_ms)
        if usage:
            cfg.track_tokens(usage.get("input_tokens", 0), usage.get("output_tokens", 0))

        log.info("tool.success", tool="style_advisor", latency_ms=latency_ms)
        return response.content
    except Exception as exc:
        cfg.track_error()
        log.error("tool.error", tool="style_advisor", error=str(exc))
        raise ToolException(f"style_advisor failed: {exc}") from exc
```

The same pattern applies to `room_planner.py`, `trend_spotter.py`, and the agent node — each with its own AI Config key and fallback prompt.

---

## Done

When you finish Phase 7 and the audience sees the dashboard telling the whole story, you've demoed the entire LaunchDarkly AI iteration loop. Close with the refrain: *one loop — ship, observe, iterate, reship — all without a redeploy.*
