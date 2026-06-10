# Moving an AI Agent to Runtime Config with LaunchDarkly, Agent Skills, and MCP

*A walk-through of lifting a LangGraph interior-design agent out of hardcoded prompts and into LaunchDarkly AI Configs — using the `launchdarkly/ai-tooling` agent skills, the LaunchDarkly MCP server, and Claude Code — without shipping a single redeploy in the process.*

---

Most teams putting LLM features into production write the first version the obvious way: the prompt lives in a Python string, the model name is pinned in a config module, and every tweak is a PR. That works until the day someone — a PM, a researcher, whoever — wants to try a different tone for premium users, or swap in a cheaper model for the half of traffic that doesn't really need Sonnet. At that point the bottleneck isn't product sense, it's release cadence. Every behavior change is a deploy.

This post walks through the alternative pattern, concretely, using a small interior-design agent called Decor Agent as the sandbox. By the end we'll have moved four prompts out of Python and into LaunchDarkly AI Configs, wired up per-user-tier targeting, proven the kill switch works in the browser, and done all of it from inside Claude Code through a set of published agent skills. If you want to follow along, the repo is `arober39/decor-agent`.

Before we get there, a quick tour of three LaunchDarkly surfaces that are easy to conflate and that this walk-through relies on.

## The three moving parts

**AI Configs** are LaunchDarkly's runtime-managed container for an LLM call. One AI Config holds one or more *variations*; each variation pins a model (e.g. `claude-sonnet-4-6`), a prompt (messages in completion mode or instructions in agent mode), and parameters like `max_tokens` and `temperature`. Targeting rules on the config decide which variation a given user context receives, and the whole thing is fetched at request time through the LaunchDarkly AI SDK — so changing a prompt or swapping a model is a UI edit rather than a deploy. AI Configs also host judges (LLM-as-a-judge evaluators) that score real responses in the background, and they integrate with the LaunchDarkly Playground for offline eval runs against labeled datasets.

**LaunchDarkly agent skills** are text-based playbooks published at `launchdarkly/ai-tooling` that teach a coding assistant how to perform common LaunchDarkly workflows — creating a flag, building an AI Config, attaching a judge, setting targeting rules. They're not API access on their own; they ride on top of the MCP server. The catalog groups into feature-flag skills, AI-Config skills, metrics skills, and onboarding skills, and installing the plugin drops all of them into `.claude/skills/`.

**The LaunchDarkly MCP server** is what actually executes LaunchDarkly API calls from inside the coding assistant. MCP (Model Context Protocol) is an open standard for letting AI clients talk to external systems through typed tools; LaunchDarkly's hosted MCP server exposes feature-flag, AI-Config, environment, and code-reference tools like `create-ai-config`, `create-feature-flag`, and `get-flag`. Agent skills call these tools under the hood. Without the MCP server connected, skills can describe what to do but can't actually do it.

The short version: **MCP server = the hands, agent skills = the playbook, AI Configs = the artifact you're managing.**

> [SCREENSHOT: concept diagram showing the three-layer relationship — MCP server as the execution layer, agent skills as the playbook layer, AI Configs as the managed artifact.]

With the vocabulary straight, we can start moving.

## The agent we're going to instrument

Decor Agent is a LangGraph service that takes free-text design questions and returns opinionated recommendations. The main agent routes each question to one of three specialist tools — `style_advisor` for palette and material questions, `room_planner` for dimensional reasoning, `trend_spotter` for what's current — and synthesizes a short response. The README frames it as *"a production-grade LangGraph agent that gives confident, specific interior design advice, built to demonstrate the LaunchDarkly AI iteration loop."*

> [SCREENSHOT: Decor Agent GitHub README showing the project description and the embedded "Design Chat" UI mockup.]

On day zero, the four prompts (main agent plus three specialists) are hardcoded in `app/prompts.py`, and every tool instantiates its own `ChatAnthropic` client with a model string baked in. It works. It's also the version we want to refactor away from, because every meaningful change to the agent right now costs a deploy.

## Why the loop needs to look different from CI/CD

There's a framing slide in the original demo that's worth translating into prose because it does a lot of quiet work. On one side, the classic CI/CD infinity loop — code, build, test, release, deploy, operate, monitor — labeled **deterministic outputs**. On the other, a different loop: Build (AI Config + Agent Skills) → Eval offline (Playground + datasets) → Release (rollout + targeting) → Eval online (judges scoring live traffic) → Monitor (latency, cost, errors) → Iterate (failures → new data) → back to Build. Label: **non-deterministic outputs**.

The argument, stripped down, is this. Traditional software leans on CI/CD because given the same inputs and code, the outputs are predictable; you write tests that pin behavior and trust them across releases. LLM-backed systems cannot. Same prompt, same model, same day — outputs drift, trend claims age, user context shifts underneath you. That's why the AI loop needs *continuous online evaluation*, *runtime-managed prompts*, and *gradual rollouts with observability baked in* rather than a test suite and a deploy button. The shape is familiar but the primitives are different, and LaunchDarkly is one opinionated answer to what those primitives should look like.

> [SCREENSHOT: the split-frame slide showing the AI iteration loop (non-deterministic) next to the CI/CD infinity loop (deterministic).]

## Installing the skills (and understanding what you just installed)

The `launchdarkly/ai-tooling` repo is the entry point. Its README enumerates every skill the plugin installs — 24 of them at the time of this post — grouped into four sections.

**Feature Flags** — `launchdarkly-flag-discovery`, `launchdarkly-flag-create`, `launchdarkly-flag-targeting`, `launchdarkly-flag-cleanup`. These are the classic LaunchDarkly workflows wrapped up as playbooks. You'll use `launchdarkly-flag-create` in about thirty seconds to build the kill switch.

**AI Configs** — `aiconfig-create`, `aiconfig-migrate`, `aiconfig-update`, `aiconfig-variations`, `aiconfig-tools`, `aiconfig-projects`, `aiconfig-online-evals`, `aiconfig-targeting`. These are where most of the work in this walk-through lives. `aiconfig-migrate` is especially nice if you're retrofitting an existing hardcoded-prompt app — it walks a five-stage migration rather than making you figure out the shape yourself.

**Metrics** — `launchdarkly-metric-choose`, `launchdarkly-metric-create`, `launchdarkly-metric-instrument`. Relevant once you want to gate rollouts on error rate, latency, or custom quality metrics.

**Onboarding** — `onboarding` and its nested workflows (`mcp-configure`, `sdk-install`, `first-flag`). The one you'll care about on day one is `mcp-configure`, which wires up the MCP server in Claude Code or Cursor.

> [SCREENSHOT: the `launchdarkly/ai-tooling` README showing the Feature Flags and AI Configs skill tables side by side.]

Installation in Claude Code is `/plugin install`, search "LaunchDarkly" or paste the repo URL, authenticate with a LaunchDarkly API token, done. If you'd rather install from the command line, you can run `npx --yes skills add launchdarkly/ai-tooling --full-depth --skill '*' --agent claude-code -y`, which lays the skills into `.claude/skills/` in the current worktree and makes them available the next time Claude Code loads skills for that directory.

There's a security note worth surfacing. Running these skills means giving your assistant permission to mutate your LaunchDarkly account — create projects, write variations, flip flags. Snyk flags several of the AI-Config skills as High/Med risk for exactly that reason. Read what a skill does before approving it, and scope the API token to the minimum roles required. Neither point is a dealbreaker, but neither is a footnote either.

> [SCREENSHOT: Claude Code transcript showing "Installed all 24 LaunchDarkly skills to `.claude/skills/`" and the Snyk risk callout below it.]

## Verifying the MCP server without leaking your key

Once the plugin is installed, the MCP server should be live. The quick sanity check is to ask Claude Code to confirm the connection — and to do it carefully, because `claude mcp list` prints the API key inline in the command string. If you share the session transcript anywhere, the key goes with it.

A clean prompt looks like *"verify the LaunchDarkly MCP server is connected without exposing my API key,"* and a good response looks like:

> LaunchDarkly MCP server is ✓ Connected.
>
> Heads up: `claude mcp list` prints the API key inline in the command string, so it appeared in my tool output for this turn. If that transcript is shared anywhere, consider rotating the key at https://app.launchdarkly.com/settings/authorization.

That's the MCP server doing its job — translating a natural-language request into an authenticated call to `app.launchdarkly.com/api/v2/...`, with the agent skill telling the assistant *how* to make that call responsibly.

> [SCREENSHOT: Claude Code transcript showing the MCP-connection check and the key-rotation warning.]

## Creating the project

Every LaunchDarkly artifact lives in a project, so step one is `aiconfig-projects`. The skill's description reads *"Create and manage projects to organize AI Configs,"* which is almost but not quite what it does — LaunchDarkly has one kind of project, and it holds feature flags, AI Configs, metrics, and segments together. `aiconfig-projects` creates a standard project framed from an AI-workflow entry point, which is fine as long as you don't expect a separate "AI project" type to exist elsewhere in the product.

A well-behaved invocation looks like the skill reading its own `quick-start.md`, POSTing to `/api/v2/projects`, and returning a confirmation:

> Project created.
>
> `decor-agent demo` (key: `decor-agent-demo`) — HTTP 201
>
> - Tags: `ai-configs`, `demo`
> - Environments: Test (`sdk-***5b8f`), Production (`sdk-***c516`)
>
> SDK keys were returned by the API but not printed — only last-4 shown.

Two small details worth calling out. First, the project spawns both Test and Production environments automatically; if you want a different environment layout you need to create them explicitly. Second, the skill surfaces only the last four characters of each SDK key in the transcript — the full keys exist in LaunchDarkly but don't leak through the chat log. That's the kind of guardrail you want to notice and trust.

> [SCREENSHOT: Claude Code transcript showing the "read quick-start → POST → verify" narration followed by the HTTP 201 confirmation with masked SDK keys.]

## The kill switch is still the most important flag you'll build

Before any AI Config exists, build a boolean feature flag called `decor-agent-enabled` and wrap the chat endpoint in it. The playbook is `launchdarkly-flag-create`; the code patch is six lines in `server.py` that checks the flag before running the agent and returns a friendly maintenance message when it's off.

The value of this flag gets undersold because it sounds trivial, but it's the single most important primitive in any AI feature. When your LLM provider has an outage, when a prompt change starts leaking PII into responses, when you ship a regression nobody caught — you want one toggle, one click, and the bad behavior is gone. No redeploy. No frantic `git revert`. Just off.

The demo version of this is deeply satisfying. Send a real question to the Decor Agent at `localhost:8000`, get a normal structured response, toggle `decor-agent-enabled` off in the LaunchDarkly UI, send another question immediately, and watch the chat render:

> Decor Agent is temporarily unavailable for maintenance. Check back soon!

That's the flag propagating through the LaunchDarkly streaming connection and taking effect on the very next request. Toggle it back on and the agent resumes as if nothing happened.

> [SCREENSHOT: the Decor Agent "Design Chat" UI showing a normal assistant response immediately followed by the maintenance-mode message after the kill switch fires.]

The structured server log for this moment is worth looking at once, because it tells you exactly what changed and where. You'll see `http.request` lines for static assets serving normally, followed by `chat.request`, `run_agent.start`, `input_guard.pass`, then `ai_config.fetched config_key=decor-agent-main source=launchdarkly variation=None model=claude-sonnet-4-20250514`, `agent.invoke`, `response_formatter.done routed_to=direct`, `run_agent.done`. Toggle the flag off and the very next request shows `chat.maintenance_mode flag_key=decor-agent-enabled` instead of the agent invocation chain. Every change is timestamped; every config fetch is attributed to LaunchDarkly rather than the hardcoded fallback.

That `variation=None` line in the log is a subtle teaching moment. It means the AI Config exists but targeting hasn't been promoted to fallthrough yet, so the SDK fell back to the default pinned in code. We'll fix that next.

> [SCREENSHOT: structured JSON server logs showing the `ai_config.fetched` line and the subsequent `chat.maintenance_mode` line after the kill switch fires.]

## Lifting the prompts into AI Configs

With the kill switch in place and the MCP server confirmed, we can move the four prompts out of Python. The four AI Configs to create are:

| Config key | Purpose |
|---|---|
| `decor-agent-main` | Main orchestrator / router |
| `decor-style-advisor` | Style specialist tool |
| `decor-room-planner` | Room planner specialist |
| `decor-trend-spotter` | Trend specialist |

The skill is `aiconfig-create`. For each config, pick completion mode (simpler than agent mode for this demo), set the initial variation to `v1-baseline`, paste in the current prompt from `app/prompts.py` verbatim, pick a model (the video uses `claude-sonnet-4-6` across the board; a real rollout might use Haiku for the style advisor and Sonnet elsewhere), and set `max_tokens` and `temperature`.

The corresponding code-side refactor is small but critical. Every tool that used to do `ChatAnthropic(model="...", system_prompt=...)` now does:

```python
cfg = get_completion_config("decor-style-advisor", context, default)
llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature)
response = llm.invoke([
    SystemMessage(cfg.system_prompt),
    HumanMessage(user_question),
])
cfg.track_success()
cfg.track_tokens(usage.input_tokens, usage.output_tokens)
```

`cfg` is a thin wrapper that knows where it came from — LaunchDarkly at runtime, or a local fallback when `LD_SDK_KEY` isn't set. This is non-negotiable if you want your team to actually adopt the pattern. Local development and unit tests keep working in offline mode against the original hardcoded prompts, and the CI pipeline doesn't grow a dependency on LaunchDarkly reachability.

The telemetry calls matter too. `cfg.track_success()`, `cfg.track_tokens(...)`, and `cfg.track_duration(...)` are how LaunchDarkly ties real request outcomes back to the variation that served them — which is what makes guarded rollouts and online evals meaningful later.

## A brief aside on skill discipline

Halfway through the video there's a reflective moment worth repeating in print. The assistant makes a mistake — falls back to raw `curl` to hit the LaunchDarkly API because the MCP tool schema looked incomplete, and gets the request body shape wrong. When the user asks for a postmortem:

> Honest answer: your prompt was fine. The failures were on my end — I didn't consult the skill's references before executing, then fell back to REST with the wrong body shape. No reasonable prompt phrasing would have saved me from that; I needed to read first, probe second, execute third.

The user then turns the lesson into a rule:

> can you ensure that you always reference the skills before executing

And the assistant writes it to memory:

> Yes. Saving this to memory so it persists across sessions. From now on, whenever a skill is invoked, I'll read the `SKILL.md` plus every file in `references/` before any tool call, probe with one throwaway resource before bulk-executing, and never default to raw `curl` as a workaround for an MCP schema gap without re-reading the skill first.

That's not a LaunchDarkly feature, but it's a pattern worth stealing. When your assistant is wired to run agent skills that mutate SaaS accounts, make "read the skill, then act" a first-class rule and persist it. A lot of flaky agentic behavior collapses into reliability once that discipline is baked in.

> [SCREENSHOT: Claude Code memory-save confirmation showing the "read the skill, then act" rule.]

## Variations: one config, multiple personalities

Now the payoff starts to earn its keep. On `decor-agent-main`, add two variations alongside `v1-baseline`:

**`budget-conscious`** — appends to the agent system prompt: *"Lead with accessible brands (IKEA, Target, Wayfair, Article); include approximate USD prices; when naming a high-end piece, offer an accessible alternative immediately; mention DIY, thrift, or secondhand when genuinely viable; flag splurges explicitly; respect tight budgets."*

**`luxury-curator`** — appends instead: *"Lead with designer and trade brands (Design Within Reach, B&B Italia, Pinch London, Knoll); name specific designers when relevant; specify materials precisely ('hand-rubbed unlacquered brass,' 'mohair velvet,' 'rift-sawn white oak'); skip mass-market references entirely. IKEA does not appear in this mode."*

Both variations still use `claude-sonnet-4-6` at `max_tokens=1024`, `temperature=1.0`. The behavior difference is entirely in the prompt.

> [SCREENSHOT: LaunchDarkly AI Configs Variations tab for Decor Agent Main showing all three variations (`v1-baseline`, `budget-conscious`, `luxury-curator`) with the prompt content visible in the expanded variation blocks.]

Each variation also has slots for attaching tools (for function calling) and judges (for online evals). The Add Judge button is the hook for the `aiconfig-online-evals` workflow — LLM-as-a-judge evaluators that run in the background on real responses and return 0–1 scores. A judge is itself an AI Config with an evaluation prompt, and every response from the variation gets scored by every attached judge. *Online evaluations work with completion-mode AI Configs; for agent-mode variations, judges get invoked programmatically through the AI SDK instead.*

The Playground tab in the same sidebar is where offline evals live — upload a labeled dataset of design questions, select which variations to compare, attach criteria like factuality or budget adherence, and read the side-by-side scorecard. We're not using it in this walk-through but it's the natural next step, and it's worth knowing where it lives.

## Targeting: the payoff frame

Switch from the Variations tab to Targeting. Three stacked rules do all the work:

```
IF user-tier IS "premium" → serve luxury-curator
IF user-tier IS "free"    → serve budget-conscious
DEFAULT                   → serve budget-conscious
```

The variation-selection panel at the top confirms the state: *"AI Config is On — serving variations based on rules."* The footer note is easy to miss but important: *"If LaunchDarkly is unreachable, SDKs will serve the default defined in your code."* That's why we kept `app/prompts.py` around as a fallback. Runtime config is great until the config service has an outage, and then you want graceful degradation rather than a broken endpoint.

> [SCREENSHOT: LaunchDarkly Targeting tab for `decor-agent-main` showing the premium and free attribute rules, the default rule, and the "If LaunchDarkly is unreachable" fallback text.]

This is the moment the whole refactor has been building toward. The same agent endpoint, same user message, now returns a recommendation priced for a premium user if their context ships with `user-tier: premium` and a recommendation priced for a free user otherwise. Same code path. Same Python module. Different answers.

For the demo to work end-to-end, the server needs to stamp `user-tier` onto the LaunchDarkly context it builds for each request. In `server.py`:

```python
# In build_context()
tier = "premium" if context_key.startswith("premium-") else "free"
builder.set("user-tier", tier)
```

In production you'd pull the tier from a session, a JWT, or a database lookup, not a context-key prefix. For a demo, the prefix trick makes it easy to switch personas live: hand the browser a context key of `premium-alice` and the same question that was returning Article recommendations five seconds ago starts returning Pinch London mohair-velvet sofas.

## What this buys you

At the end of all this you have an agent whose behavior is configurable at runtime, segmentable by user context, and gracefully degradable when the config service is unreachable. Every prompt is a row in LaunchDarkly instead of a string in Python. Every model is a field you can change from the UI instead of a deploy trigger. The kill switch is one toggle. The variations are additive. The targeting is declarative.

And because the wiring goes through the AI SDK, you get the downstream surfaces for free as you want them. Add a judge to any variation for continuous scoring of live traffic. Upload a dataset to the Playground for offline evals before any rollout. Define metrics and start a guarded rollout that ramps a new variation from 10% to 100% with auto-rollback if error rate, p95 latency, or a custom quality metric breaches its threshold.

That closing set of phases didn't make it into the video we're walking through here — it's the right-hand half of the AI iteration loop slide, and it's the natural second post in this series. But the left half, the part we did cover, is already enough to change how your team ships LLM features. Configuration, not code. Targeting, not conditionals. One loop — ship, observe, iterate, reship — all without a redeploy.

> [SCREENSHOT: presenter outro frame for the social-card / hero image.]

---

## Screenshot placeholder index

Every `> [SCREENSHOT: ...]` block above corresponds to a frame that should be captured from the source video or re-recorded against the final LaunchDarkly UI:

1. Concept diagram — MCP server (hands) + agent skills (playbook) + AI Configs (artifact)
2. Decor Agent GitHub README with Design Chat mockup
3. AI iteration loop vs CI/CD infinity loop split slide
4. `launchdarkly/ai-tooling` README with Feature Flags + AI Configs tables
5. Claude Code transcript: `npx skills add` confirmation + Snyk risk callout
6. Claude Code transcript: MCP connection verified + API key rotation warning
7. Claude Code transcript: project created with masked SDK keys
8. Decor Agent chat UI showing normal response then maintenance message
9. Server logs showing `ai_config.fetched` then `chat.maintenance_mode`
10. Claude Code memory save: "read the skill, then act" rule
11. LaunchDarkly AI Configs Variations tab — three variations visible
12. LaunchDarkly Targeting tab — premium/free/default rules
13. Presenter outro frame (hero or closing image)

---

## Sources

- [LaunchDarkly AI Configs overview](https://launchdarkly.com/docs/home/ai-configs)
- [LaunchDarkly AI Configs variations](https://launchdarkly.com/docs/home/ai-configs/create-variation)
- [LaunchDarkly AI Configs targeting](https://launchdarkly.com/docs/home/ai-configs/target)
- [LaunchDarkly AI Configs quickstart](https://launchdarkly.com/docs/home/ai-configs/quickstart)
- [LaunchDarkly online evaluations](https://launchdarkly.com/docs/home/ai-configs/online-evaluations)
- [Agents in AI Configs](https://launchdarkly.com/docs/home/ai-configs/agents)
- [Completion mode vs agent mode](https://launchdarkly.com/docs/tutorials/agent-vs-completion)
- [Agent Skills quickstart](https://launchdarkly.com/docs/tutorials/agent-skills-quickstart)
- [launchdarkly/ai-tooling on GitHub](https://github.com/launchdarkly/ai-tooling)
- [LaunchDarkly MCP server docs](https://launchdarkly.com/docs/home/getting-started/mcp)
- [launchdarkly/mcp-server on GitHub](https://github.com/launchdarkly/mcp-server)
