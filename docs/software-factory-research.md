# Software factory approaches — notes for Decora

Planning notes, not a video script. Sources are first-party where possible. This is how other people build **plants that produce software**, and what that should include for Decora (the design agent and the repo that ships her). It is not A2A. A2A stays a later video: Decora talking to another business agent.

## Two meanings of “factory” — pick one per sentence

**Platform / DevSecOps factory** (DoD, Platform One): people, pipelines, environments, and gates that continuously deliver artifacts. Humans still write most of the code. The factory is the *line*. [DoD Enterprise DevSecOps Strategy Guide](https://dl.dod.cyber.mil/wp-content/uploads/devsecops/pdf/DoDEnterpriseDevSecOpsStrategyGuide.pdf).

**Agentic software factory** (Factory.ai, OpenAI’s Codex loop): coding agents as stations on that line. Signals in (bugs, evals, issues) → plan → implement → test → review → ship → new signals. Humans set intent and hold the gate. [Factory 2.0](https://factory.ai/news/software-factory), [Pragmatic Engineer on OpenAI](https://newsletter.pragmaticengineer.com/p/openai-software-factory).

For Decora you want the second, sitting on a small version of the first. You already have the product agent (`decor-design` + harness + goose). The factory is how **coding agents** keep shipping her without the job living in a chat.

## What companies are actually doing

### Factory.ai — “signal to production”

Droids cover triage, plan, execute, review, release. Recipes on a schedule. Model-independent. Governance they name in public: per-repo validation gates, command allow/deny lists, audit trail, secrets out of context. [Software Factory product](https://factory.ai/product/software-factory).

Steal for Decora: a **recipe per job type** (not one mega-agent). Allow/deny is host-side. Do not buy their product to learn the shape.

### OpenAI — Codex as the plant

Internal loop around Codex: agent implements, runs tests, babysits CI until green, specialist review agents, then production monitors kick more agents. Humans still merge. [Inside OpenAI’s agentic software factory](https://newsletter.pragmaticengineer.com/p/openai-software-factory).

Steal for Decora: **CI is the evaluator**. One “done” is `test_mcp_*.py` + harness tests green, not a paragraph that says it works. Specialist reviewers later (SKU honesty, UI, protocol) — not one generic “review this PR.”

### Anthropic — harness, not a bigger prompt

Planner / generator / evaluator. Sprint contracts: agree what “done” is before code. Structured artifacts handed between sessions. [Harness design for long-running apps](https://www.anthropic.com/engineering/harness-design-long-running-apps).

Steal for Decora: you already slice in `docs/aaif-learning.md`. Make each factory job a **contract**: files in, tests that must pass, stop condition. That is the same idea as `request_approval` on the design agent.

### The older factory (DoD)

Pipelines, named environments, artifacts, continuous monitoring. Useful so you do not invent a new word for CI + git + tests. Useless as the Decora *story* if you stop there — that factory has no agent stations.

## Standards that are actually emerging (AAIF)

Linux Foundation [AAIF](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation) hosts the stack you already chose. [A2A joining AAIF](https://aaif.io/blog/a2a-joins-aaif) names the layers:

| Layer | Project | Decora today | Factory use |
| --- | --- | --- | --- |
| Instructions | [AGENTS.md](https://agents.md/) (OpenAI, now AAIF) | File exists, but it is written for **hosts of `decor-design`**, not for coding agents on the repo | Split or nest: design-host rules vs “how to build Decora” |
| Runtime | goose | Second host of the catalog | Optional worker that runs a *repo* recipe, still no developer cheat |
| Agent → tools | MCP | `decor-design` | Coding agents keep using MCP/IDE tools; do not invent a private function |
| Traffic / policy | agentgateway | Not yet | Only when more than one thing to front (your README already says this) |
| Agent → agent | A2A | Not yet | Retailer / stock. **Not** the factory. Different video. |

AAIF’s own split: MCP is how an agent uses tools; A2A is how two agents with separate maintainers hand off work; AGENTS.md is how a *project* tells a coding agent the local rules. Mixing those in one video is how the factory becomes a metaphor again.

**Not AAIF, but showing up:** [agentharnesses.io](https://agentharnesses.io/specification) (`HARNESS.md` + progressive disclosure). Treat as an experiment, not a standard you owe the series. Agent Skills (`SKILL.md`) are already how Cursor/Claude Code package playbooks — you have those for LaunchDarkly; you can add Decora *build* skills the same way.

Microsoft NLWeb (sites queryable by agents) is for the website, not for the factory that ships the agent.

## What the Decora factory should include

Keep it on her product surface.

**Already in the plant**

- World + home on MCP (`search_catalog`, `project://`, `request_approval`)
- Host harness (observe → tools → stop). Approve is not a tool
- Goose recipe with developer tools off
- Slice log (`docs/aaif-learning.md`) and one-sentence commits

**Build next (factory, still not A2A)**

1. **A coding-agent `AGENTS.md` (or nested file)** that OpenAI’s convention actually describes: how to install, which tests to run, commit rule, “do not invent SKUs in fixtures,” “do not mix a backlog drive-by into this PR.” The current root `AGENTS.md` is stop conditions for *furnishing a room*. Coding agents will misread it as how to patch Python.

2. **Job recipes / skills for workers**, one job each: add a catalog row, add a host route, add a learning-log slice. Each names inputs, files, and the test that is “done.” Anthropic’s sprint contract, Factory’s recipe, your existing slice habit.

3. **Evaluator that is not a chat.** `test_catalog.py`, `test_mcp_*.py`, `test_harness.py`, Studio HTTP tests. The worker loops until green or it stops for a human. OpenAI’s CI babysitter, smaller.

4. **Host policy for the workers**, same philosophy as Decora: allow/deny commands, secrets never in the prompt, human merge. You already refuse `approve` on the design agent. The factory equivalent is: the coding agent does not force-push `main` and does not skip hooks.

5. **Signals that are hers.** Failed SKU-honesty, empty search, Studio “list not locked,” budget over cap. Those tickets become factory jobs. Production monitors feeding Codex is OpenAI’s version; you start with tests and Studio QA scripts you already have.

6. **Specialist review later**, if at all: one agent that only checks “every SKU in the diff exists in the PIM,” one that only checks MCP tools still match `tools/list`. Not a generic PR bot.

**Leave out of this track**

- A2A, Agent Cards, retailer agents — next series video
- agentgateway — still “only when there is more than one thing to front”
- Buying Factory.ai / standing up a DoD platform — you need the *loop*, not their brand

## Suggested order of moves

A2A implementation can proceed on its own branch. Factory work that unblocks coding agents on `main`:

1. Nested or second `AGENTS.md` for **repo workers** (AAIF/OpenAI convention).
2. One skill or goose/Cursor recipe: “add a PIM row + photo + test” end to end until tests pass.
3. Make CI the stop condition for that recipe.
4. Only then: a second recipe (host route, learning-log slice).
5. Signals: turn one real Decora failure mode into a ticket the recipe can pick up.

If a slice does not make a coding agent more able to ship Decora without chatting you the design, it is not factory work. If it makes her talk to a store, it is A2A.
