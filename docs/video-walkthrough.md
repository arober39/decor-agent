# The LaunchDarkly AI Iteration Loop — A Written Walkthrough

A step-by-step companion to the `ai-iteration-loop-final-copy.mp4` video demo. Each section maps to a stretch of the video, explains what's happening on screen, and fills in the LaunchDarkly concepts (AI Configs, agent skills, MCP server) that the video moves through quickly.

Screenshots are marked with `> [SCREENSHOT: ...]` placeholders so the final post can be illustrated without rerecording anything.

---

## Before we start: three pieces of LaunchDarkly you'll see used in the video

The demo leans on three distinct LaunchDarkly products that are easy to conflate, so it's worth separating them up front.

**AI Configs** are LaunchDarkly's runtime-managed container for an LLM call. A single AI Config holds one or more *variations*, where each variation pins a specific model, a prompt (messages in completion mode, or instructions in agent mode), and parameters like `max_tokens` and `temperature`. Targeting rules decide which variation a given user context receives, and the whole thing gets fetched at request time through the LaunchDarkly AI SDK — so changing a prompt or swapping a model is a UI edit rather than a deploy. AI Configs also host **judges** (LLM-as-a-judge evaluators) that score real responses in the background for online evals, and they integrate with LaunchDarkly's **Playground** for offline evaluations against labeled datasets.

**LaunchDarkly agent skills** are text-based playbooks published at `launchdarkly/ai-tooling` that teach a coding assistant like Claude Code or Cursor *how* to perform common LaunchDarkly workflows — creating a flag, building an AI Config, attaching a judge, setting targeting rules, and so on. They're not API access on their own; they're workflow overlays that ride on top of the MCP server. The full catalog is grouped into feature-flag skills, AI Config skills, metrics skills, and onboarding skills.

**The LaunchDarkly MCP server** is what actually executes LaunchDarkly API calls from inside the coding assistant. MCP (Model Context Protocol) is an open standard for letting AI clients talk to external systems through structured tools, and LaunchDarkly ships a hosted MCP server that exposes feature-flag, AI-Config, environment, and code-reference tools (`create-ai-config`, `create-feature-flag`, `get-flag`, etc.). Agent skills call these tools under the hood; without the MCP server connected, skills can describe what to do but can't actually do it.

The short version: **MCP server = the hands, agent skills = the playbook, AI Configs = the thing you're managing.**

> [SCREENSHOT: concept diagram showing MCP server (hands) + agent skills (playbook) + AI Configs (artifact). Optional — a simple three-panel illustration.]

---

## 0:00 – 0:40 — Cold open: presenter intro

The video opens with the presenter on camera in a warmly lit home workspace, introducing the demo and setting expectations. This is the hook: *we're going to move an AI agent from hardcoded prompts to runtime-managed configuration, and we're going to do it live, without a redeploy.*

> [SCREENSHOT: presenter at ~0:20, kitchen backdrop, burgundy sweater — opening shot.]

---

## 0:40 – 2:00 — Meet the Decor Agent

Cut to the GitHub page for `arober39/decor-agent`, the agent we're about to instrument. The README describes it as *"a production-grade LangGraph agent that gives confident, specific interior design advice. Built to demonstrate the LaunchDarkly AI iteration loop — AI Configs for runtime-managed prompts and models, progressive release, online evals, and observability."*

Under "What it does," the README explains the architecture: users send questions to Decora, a senior interior-design advisor, and the main agent routes each question to one of three specialist tools and then synthesizes a short opinionated response.

The example questions double as a map of the specialist tools you'll see referenced later:

- *"What paint color works with dark oak floors?"* → `style_advisor`
- *"I have a 12x14 living room with a $2000 budget"* → `room_planner`
- *"Is terrazzo still trending?"* → `trend_spotter`

The embedded "Design Chat" mockup in the README previews what users see at `localhost:8000`.

> [SCREENSHOT: `arober39/decor-agent` README showing the project description and the Design Chat mockup.]
>
> [SCREENSHOT: "What it does" section showing the three example questions mapped to specialist tools.]

---

## 2:00 – 3:45 — The framing slide: AI iteration loop vs. CI/CD

The most conceptually important frame in the video. A single slide puts two loops side by side.

On the right, **the AI iteration loop**: Build (AI Config + Agent Skills) → Eval offline (Playground + datasets) → Release (5% rollout + targeting) → Eval online (judges score live traffic) → Monitor (latency, cost, errors) → Iterate (failures → new data) → back to Build. The label above the loop reads **non-deterministic outputs**.

On the left, **classic CI/CD**: the familiar blue/green infinity loop of code → build → test → release → deploy → operate → monitor → plan. Label: **deterministic outputs**.

The argument: traditional software can lean on CI/CD because given the same inputs and code, the outputs are predictable. You write tests that pin behavior. LLM-backed systems cannot. Same prompt, same model, same day — the output might still drift, the trends it cites might go stale, user context might shift. That's why the AI loop needs *continuous online evaluation*, *runtime-managed prompts*, and *gradual rollouts with observability baked in*. The shape of the loop is familiar, but the primitives it runs on are different.

This is the thesis the rest of the video demonstrates in code.

> [SCREENSHOT: the full split slide — "NON DETERMINISTIC OUTPUTS" with the AI iteration loop on the upper right, "DETERMINISTIC OUTPUTS" with the CI/CD infinity loop on the lower left.]

---

## 3:45 – 4:30 — The agent-skills catalog

The video navigates to `github.com/launchdarkly/ai-tooling`, the official agent skills repo. The README lays out every skill the plugin installs. There are four skill groups — this list is worth pausing on because the next several minutes are driven by invoking these one after another.

**Feature Flags**
- `launchdarkly-flag-discovery` — audit flags and identify stale or launched flags
- `launchdarkly-flag-create` — create new flags that match existing codebase patterns
- `launchdarkly-flag-targeting` — manage targeting, rollouts, rules, cross-environment config
- `launchdarkly-flag-cleanup` — safely remove flags from code

**AI Configs**
- `aiconfig-create` — build AI Configs with variations for agent or completion mode
- `aiconfig-migrate` — walk a hardcoded-prompt app through a five-stage migration to AI Configs
- `aiconfig-update` — manage AI Config lifecycle (updates, deletions)
- `aiconfig-variations` — handle A/B testing through variations
- `aiconfig-tools` — develop and attach tools for function calling
- `aiconfig-projects` — organize AI Configs within projects
- `aiconfig-online-evals` — attach LLM-as-a-judge evaluators
- `aiconfig-targeting` — set up targeting rules for rollouts

**Metrics**
- `launchdarkly-metric-choose` — pick the right metric type for an experiment
- `launchdarkly-metric-create` — build metrics and instrument tracking events
- `launchdarkly-metric-instrument` — add tracking calls to existing metric definitions

**Onboarding**
- `onboarding` — end-to-end setup (roadmap, MCP, SDK, first flag)
- `onboarding/mcp-configure` — configure the LaunchDarkly MCP server
- `onboarding/sdk-install` — detect, plan, and install the correct SDK
- `onboarding/first-flag` — create and toggle a boolean flag as proof of concept

Installation in Claude Code is straightforward: `/plugin install`, search "LaunchDarkly" (or paste the repo URL), authenticate with a LaunchDarkly API token, and the skills plus the MCP server wire themselves up together.

> [SCREENSHOT: the `launchdarkly/ai-tooling` README showing the Feature Flags and AI Configs skill tables.]
>
> [SCREENSHOT: the Metrics and Install as a Claude Code Plugin sections further down the same page.]

---

## 4:30 – 5:00 — Claude Code home, workspace selection

The video switches over to Claude Code. The home panel reads *"What's up next, Alexis?"* with aggregate usage stats — sessions, messages, token totals, peak hour, favorite model — and a contribution-graph-style activity heatmap. A workspace picker at the bottom lets you select which project Claude Code should operate in; the video picks `decor-agent`.

This is a small beat but worth noting: everything that follows happens inside Claude Code with the working directory scoped to the decor-agent repo, which is what lets the agent skills read local files, edit `app/flags.py`, and so on.

> [SCREENSHOT: Claude Code "What's up next, Alexis?" home screen with usage stats and the workspace dropdown showing `decor-agent`.]

---

## 5:00 – 5:30 — Installing the agent skills

The video shows the installation command being run:

```
npx --yes skills add launchdarkly/agent-skills --full-depth --skill '*' --agent claude-code -y
```

The response confirms: *"Installed all 24 LaunchDarkly skills to `.claude/skills/` in this worktree. They'll be available next time Claude Code loads skills for this directory."*

There's a helpful security note in the same response — Snyk flagged a handful of skills (`aiconfig-create`, `aiconfig-online-evals`, `aiconfig-projects`, `aiconfig-targeting`, `aiconfig-tools`, `aiconfig-update`, `mcp-configure`, `apply`) as High/Med risk because they execute with full agent permissions. The callout is a nice real-world touch: installing skills is giving an assistant the ability to act on your LaunchDarkly account, and you should read what they do before running them.

> [SCREENSHOT: Claude Code transcript showing the `npx skills add ...` command and the "Installed all 24 LaunchDarkly skills" confirmation, including the Snyk risk callout.]

---

## 5:30 – 6:00 — Verifying the MCP server without leaking the key

The next Claude Code prompt asks the sensible question: *"can you verify the launchdarkly mcp server is connected without exposing my api key."*

Claude Code runs `Check LaunchDarkly MCP connection status` and reports back:

> LaunchDarkly MCP server is ✓ Connected.
>
> Heads up: `claude mcp list` prints the API key inline in the command string, so it appeared in my tool output for this turn. If that transcript is shared anywhere, consider rotating the key at https://app.launchdarkly.com/settings/authorization.

Two things worth understanding here. First, the MCP server is what actually turns natural-language requests like "create an AI Config" into authenticated calls against `app.launchdarkly.com/api/v2/...`. Without it, the skills would have a playbook but no way to execute. Second, the LaunchDarkly MCP server authenticates with an API access token (configurable via `--api-key` or environment variables), and the video's on-screen warning about key leakage is a real concern worth surfacing in a post.

> [SCREENSHOT: Claude Code output showing "LaunchDarkly MCP server is ✓ Connected" plus the "Heads up" rotation warning.]

---

## 6:00 – 7:00 — Creating the demo project

The conversation continues with Claude Code correcting itself mid-flow — a nice moment of transparency. After the user questions the approach ("why are you using tools when we have agent skills"), the assistant pivots:

> You're right — I was wrong. The `aiconfig-projects` skill explicitly handles project creation (see `quick-start.md:14` — it even has POST `https://app.launchdarkly.com/api/v2/projects` documented with key-detection built in). Let me invoke it properly instead of hand-rolling curl.

It then invokes the skill (`Used Skill`), follows the documented flow (*"detect key → read quick-start → POST → verify"*), and confirms success:

> Project created.
>
> decor-agent demo (key: `decor-agent-demo`) — HTTP 201
>
> - Tags: `ai-configs`, `demo`
> - Environments: Test (`sdk-***5b8f`), Production (`sdk-***c516`)
>
> SDK keys were returned by the API but not printed — only last-4 shown.

This is the `aiconfig-projects` skill doing exactly what its description promises: *"Create and manage projects to organize AI Configs."* Despite the skill's name, it creates a standard LaunchDarkly project — one that will hold feature flags, AI Configs, metrics, and segments together. There isn't a separate "AI Config project" type in LaunchDarkly.

> [SCREENSHOT: Claude Code transcript showing the skill's "read quick-start → POST → verify" narration and the "Project created" response with masked SDK keys.]

---

## 7:00 – 7:30 — The kill-switch moment in the web UI

The video switches over to `http://localhost:8000/` — the Decor Agent's own chat UI, titled *"ALEXIS & PARTNERS — Design Chat."* A user has sent *"its a 1 bedroom apartment with midcentury modern decor,"* and the agent has responded warmly with a clarifying question and a list of follow-up angles.

The user sends one more message: *"help me with choosing a color palette."* The response:

> **Decor Agent is temporarily unavailable for maintenance. Check back soon!**

That's the kill switch firing. A boolean feature flag (`decor-agent-enabled`) has been toggled off in LaunchDarkly, and the chat endpoint is now short-circuiting to a maintenance response without touching the agent graph. No deploy. No service restart. The flag change propagated through the streaming connection and took effect on the very next request.

This is the simplest LaunchDarkly primitive and also the most important one for production AI: one toggle, zero redeploys, bad behavior gone.

> [SCREENSHOT: the Design Chat UI showing the normal assistant response followed immediately by the "temporarily unavailable for maintenance" message.]

---

## 7:30 – 8:00 — The server log view

Full-screen structured JSON logs stream past in the terminal. Key lines to point out:

- `http.request method=GET path=/web/styles.css` — static assets still serve normally
- `chat.request context_key=... message_id=...` — the inbound request
- `run_agent.start` → `input_guard.pass`
- `ai_config.fetched config_key=decor-agent-main source=launchdarkly variation=None model=claude-sonnet-4-20250514`
- `agent.invoke ... has_tool_calls=False tools_selected=[] total_tokens=1515`
- `response_formatter.done routed_to=direct`
- `run_agent.done` → `chat.response`

Then the kill-switch fires, and subsequent requests show:

- `chat.maintenance_mode flag_key=decor-agent-enabled`

Two concepts the logs make concrete. First, `ai_config.fetched source=launchdarkly` tells you the prompt, the model, and the variation all came from LaunchDarkly at request time rather than from a hardcoded Python constant. Second, the `variation=None` warning is a small teaching moment — it means the AI Config exists but no targeting rule is promoted to production yet, so the SDK is falling back to the default pinned in code. Targeting is the next step.

> [SCREENSHOT: structured JSON server logs showing the `ai_config.fetched` line and the subsequent `chat.maintenance_mode` lines after the kill switch fires.]

---

## 8:00 – 9:00 — Diagnostic, reflection, memory

Back in Claude Code, a reflective exchange. The user asks what the prompt *should* have looked like, and the assistant responds with an honest postmortem:

> All 4 configs are now correct (`modelConfigKey`, `modelName`, `parameters`, `system prompt` all captured).
>
> Honest answer: your prompt was fine. The failures were on my end — I didn't consult the skill's references before executing, then fell back to REST with the wrong body shape. No reasonable prompt phrasing would have saved me from that; I needed to read first, probe second, execute third.

The user then asks it to bake that lesson in: *"can you ensure that you always reference the skills before executing."*

> Yes. Saving this to memory so it persists across sessions.
>
> Saved. From now on, whenever a skill is invoked (or a task clearly maps to one), I'll read the `SKILL.md` plus every file in `references/` before any tool call, probe with one throwaway resource before bulk-executing, and never default to raw `curl` as a workaround for an MCP schema gap without re-reading the skill first.

This is a small but meaningful beat. It's not a LaunchDarkly feature, but it's an operating pattern: *when your assistant runs agent skills that can mutate your SaaS environment, give it the rule to read the skill before executing, and persist that rule across sessions.*

> [SCREENSHOT: Claude Code transcript showing the postmortem, the user's follow-up, and the "Recalled a memory, saved 2 memories" confirmation.]

---

## 9:00 – 9:45 — Skills catalog surfaced inline

Claude Code surfaces the available AI Config skills inline to set up the next move:

```
ai-configs/aiconfig-create     Create AI Configs with variations for agent or completion mode
ai-configs/aiconfig-update     Update and delete AI Configs, manage lifecycle
ai-configs/aiconfig-variations Manage AI Config variations for A/B testing
ai-configs/aiconfig-tools      Create and attach tools for function calling
ai-configs/aiconfig-projects   Create and manage projects to organize AI Configs
ai-configs/aiconfig-online-evals Attach LLM-as-a-judge evaluators to AI Configs
ai-configs/aiconfig-targeting  Configure targeting rules for AI Config rollouts
```

Its next move is `aiconfig-targeting`, because the diagnostic in the previous step revealed the real issue: *"none of the 4 configs have a fallthrough set yet, which is why the SDK fell back to `claude-sonnet-4-20250514` in your server log."*

The proposed plan, narrated inline:

- `decor-agent-main`: fallthrough = `v1-baseline`; add attribute rules `user-tier: budget → budget-conscious` and `user-tier: premium → luxury-curator`
- `decor-style-advisor`, `decor-room-planner`, `decor-trend-spotter`: fallthrough = `v1-baseline`
- Apply to Test env first (matches your running server); Production after you verify

This is `aiconfig-targeting` doing what its description says — *"Configure targeting rules for AI Config rollouts."* Because AI Config targeting follows the same evaluation model as feature flags, the mental model transfers cleanly from LD's classic product.

> [SCREENSHOT: inline skills catalog (blue-highlighted list) plus the proposed targeting plan the assistant wrote out.]

---

## 9:45 – 10:30 — Writing the variations

Claude Code drafts the `budget-conscious` and `luxury-curator` variations for `decor-agent-main`. The prompts are appended to the existing `AGENT_SYSTEM_PROMPT`:

```
## Budget Conscious Mode

The user is budget-conscious. When recommending products or materials:
- Lead with accessible brands: IKEA, Target, Wayfair, Article, World Market, Urban Outfitters.
- Include approximate prices in USD for each named item.
- When naming a high-end piece, offer an accessible alternative immediately ...
- Mention DIY, thrift, or secondhand options when genuinely viable ...
- Flag splurges explicitly ...
```

and

```
## Luxury Curator Mode

The user values quality, craftsmanship, and distinction. When recommending:
- Lead with designer and trade brands: Design Within Reach, B&B Italia, Pinch London, Knoll ...
- Name specific designers when relevant ...
- Specify materials precisely ("hand-rubbed unlacquered brass," "mohair velvet," "rift-sawn white oak") ...
- Skip mass-market references entirely. IKEA does not appear in this mode.
```

Same config, same code path, two genuinely different answers to the same question — with no Python changes required. That's the shape of the AI Configs pattern. *Every variation defines a unique combination of model settings and prompt content; targeting rules decide which one a given context receives.*

> [SCREENSHOT: Claude Code editor pane showing the `## Budget Conscious Mode` and `## Luxury Curator Mode` prompt additions.]

---

## 10:30 – 11:15 — The LaunchDarkly AI Configs UI

Cut to `app.launchdarkly.com/projects/decor-agent-demo/ai-configs/decor-agent-main/variations?env=production`. The sidebar shows the shape of the `decor-agent demo` project: **Release** (Flags, Guarded rollouts, Segments, Contexts, Live events, Approvals), **AI** (Configs, Agent graphs, Playground, Insights, Library), **Observe** (Sessions, Errors, Logs, Traces, Observability metrics, Alerts, Dashboards).

On the right panel of the Decor Agent Main page:

- **Mode**: Completion
- **Key**: `decor-agent-main`
- **Description**: *"Main orchestrator (Decora) that routes design questions to specialist tools."*
- **Tags**: `decor-agent`

The Variations tab is selected, showing all three variations collapsed and then expanded:

1. `v1-baseline` — pinned to `claude-sonnet-4-6`
2. `budget-conscious` — pinned to `claude-sonnet-4-6`, with the system prompt visible and the "Add message / Add tools / Add judge" row available at the bottom
3. `luxury-curator` — pinned to `claude-sonnet-4-6`, same structure

Each variation shows its `max_tokens=1024` and `temperature=1` parameters, its System message, and buttons to add more messages, attach tools (for function calling), or attach a judge (for online evals). The "Add judge" button is the hook for the `aiconfig-online-evals` workflow — LLM-as-a-judge evaluators that run in the background on real responses and return 0–1 scores.

> [SCREENSHOT: LaunchDarkly AI Configs Variations tab for Decor Agent Main showing all three variations, right-hand panel with mode/key/description, sidebar navigation.]

---

## 11:15 – 12:00 — The targeting page (the payoff frame)

Switch tabs from Variations to Targeting (`.../decor-agent-main/targeting?env=production`). The payoff is right there in three stacked rules:

> AI Config is **On** — serving variations based on rules.
>
> **premium users get luxury-curator** — If `user-tier` is one of `premium`, serve `luxury-curator`
>
> **free users get budget-conscious** — If `user-tier` is one of `free`, serve `budget-conscious`
>
> **Default rule** — Serve `budget-conscious`
>
> *If LaunchDarkly is unreachable, SDKs will serve the default defined in your code.*

This is the moment the whole demo has been building to. The same agent endpoint, the same user message, now returns a recommendation priced for a premium user if their context ships with `user-tier: premium`, and a recommendation priced for a free user otherwise. The fallback-in-code note at the bottom is important too: if LaunchDarkly is unreachable, the SDK still serves the hardcoded default from `app/flags.py`, so the agent degrades gracefully rather than failing.

> [SCREENSHOT: the Targeting tab showing the two attribute rules (premium → luxury-curator, free → budget-conscious) and the default rule plus the "If LaunchDarkly is unreachable" fallback text.]

---

## 12:00 – 12:45 — Close: presenter to camera

The video closes the same way it opened — presenter on camera, direct address, wrapping the argument. This is where the narrator typically lands the main takeaway for the audience: *every change you just saw — kill switch, prompt edits, variations, targeting — happened without a redeploy. That's the AI iteration loop.*

> [SCREENSHOT: presenter at ~12:30, outro framing.]

---

## What the video demonstrated, in one table

| Phase | On-screen moment | LaunchDarkly surface used | Why it matters |
|---|---|---|---|
| Intro | Presenter hook | — | Sets up non-deterministic systems framing |
| README tour | `arober39/decor-agent` | — | Establishes the agent under test |
| Concept slide | AI loop vs CI/CD | — | Defines the thesis |
| Skills catalog | `launchdarkly/ai-tooling` README | Agent skills (24 of them) | Shows the playbook layer |
| Plugin install | `npx skills add ...` | Claude Code + agent skills | Gets the playbook into the editor |
| MCP verify | "MCP server is ✓ Connected" | MCP server | Proves the hands work |
| Project create | `aiconfig-projects` skill → POST | MCP server + `aiconfig-projects` | Creates the LD project holding everything |
| Kill switch | `localhost:8000` maintenance response | Boolean feature flag | Simplest, most important primitive |
| Server logs | `ai_config.fetched` lines | AI SDK | Proves prompts + model are runtime |
| Memory save | *"read the skill, then act"* | Claude Code memory | Operating discipline for skill use |
| Variations authored | `## Budget Conscious Mode` / `## Luxury Curator Mode` | AI Config variations | Personality per segment |
| Variations UI | LD UI variations tab | AI Configs | Runtime-managed prompt + model |
| Targeting UI | `user-tier is premium → luxury-curator` | AI Config targeting | The payoff — same code, different answers |
| Close | Presenter outro | — | Lands the refrain |

---

## What isn't shown in this video (but lives in the runbook)

The video ends on the targeting payoff. The full `DEMO_RUNBOOK.md` in this repo continues through three more phases that you'd likely want to follow up on in a companion post:

- **Offline evals** — Upload a labeled dataset of design questions to the LaunchDarkly **LLM Playground**, run it against `budget-conscious` and `luxury-curator`, and read the side-by-side scorecard. Offline evals work with completion-mode AI Configs and surface status counts, aggregate scores per criterion, latency, and token usage per variation.
- **Guarded rollouts** — Ramp a new variation 10% → 25% → 50% → 100% against custom metrics (`chat.error_rate`, `chat.p95_latency_ms`, `chat.fallback_response_rate`) with auto-rollback if any threshold breaches.
- **Online evals with LLM judges** — Attach judges via `aiconfig-online-evals` to score every real response in production on a 0–1 scale. A judge is itself an AI Config with an evaluation prompt; when the variation it's attached to generates a response, LaunchDarkly runs the judge in the background. *Online evaluations work on completion-mode AI Configs; for agent-mode variations, you invoke a judge programmatically via the AI SDK.*

Together the three make up the right half of the AI iteration loop slide — Release, Eval online, Monitor — and they're the natural second post in this series.

---

## Screenshot placeholder index

For a quick pass during editing, every `> [SCREENSHOT: ...]` block above corresponds to a frame that should be captured from the video or re-recorded against the final LaunchDarkly UI:

1. Concept illustration — MCP server / agent skills / AI Configs relationship (optional)
2. Presenter intro (~0:20)
3. Decor Agent README (hero view)
4. Decor Agent README "What it does" with example questions
5. AI iteration loop vs CI/CD split slide
6. `launchdarkly/ai-tooling` README — Feature Flags + AI Configs tables
7. `launchdarkly/ai-tooling` README — Metrics + Install as Claude Code Plugin
8. Claude Code home screen with workspace dropdown
9. Claude Code transcript: `npx skills add` + "Installed all 24 skills" + Snyk note
10. Claude Code transcript: MCP connection verified + key-rotation warning
11. Claude Code transcript: project created (`HTTP 201` + masked SDK keys)
12. Decor Agent UI at `localhost:8000` showing normal chat → maintenance message
13. Server logs: `ai_config.fetched` then `chat.maintenance_mode`
14. Claude Code transcript: skill-reading postmortem + memory save
15. Claude Code: inline skills catalog + targeting plan
16. Claude Code editor: `Budget Conscious Mode` + `Luxury Curator Mode` prompts
17. LaunchDarkly AI Configs Variations tab for `decor-agent-main`
18. LaunchDarkly Targeting tab with premium/free rules
19. Presenter outro (~12:30)

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
