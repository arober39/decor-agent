# Decora agentic software factory — build plan

Living plan. Replaces the “PIM-row recipe first” order in [`software-factory-research.md`](software-factory-research.md). That file is a survey of other companies. This file is **what we build**, in order.

The product is Decora: furnishes a room from a real catalog, writes `project://`, stops for human Approve. The **factory** is not her. It is the loop that lets **coding agents** ship her at a volume you cannot inspect by hand, with runtime control after merge.

LaunchDarkly’s word for this is an [AI software factory](https://launchdarkly.com/blog/entering-the-ai-software-factory-era/): agents on the SDLC, plus [run-side control](https://launchdarkly.com/blog/the-software-factory-stack-everyone-forgot-to-finish/) (what shipped, exposure policy, reverse one change, cleanup). Factory.ai’s nine stages (signal → … → ship/monitor) are the build-side diagram. We take both. We do not take a dark factory (lights out, no humans).

## Principles (do not skip these to “get to agents”)

1. **Specification is the job.** “Make it better” is how you get a birdhouse. Each factory job names files, binary checks, and stop. Same idea as `request_approval` on the design agent. ([Nolen / LD](https://launchdarkly.com/blog/entering-the-ai-software-factory-era/))
2. **Controlled automation, not autonomy.** Agents generate; humans own criteria and merge. An agent reviewing another agent only works with binary checks, not “is this good?”
3. **White-box and black-box.** Compiling is not done. `search_catalog` returning a SKU is white-box. Studio locking the list after Approve is black-box. Both.
4. **Build side and run side.** Tests before merge are not a gate once nobody reads the PR. Exposure, rollback of **one change**, and flag cleanup have to be in the line from day one, not bolted on after agents are opening PRs. ([Attensil / LD](https://launchdarkly.com/blog/the-software-factory-stack-everyone-forgot-to-finish/))
5. **Decora stays the KPI.** `spec_approved` is the product metric. Token spend and PR count are not.

## What is already in the plant

| Piece | Role |
| --- | --- |
| `decor-design` + harness | The product agent. Not a factory station. |
| Goose recipe, developer off | Proof a stranger can *use* her. Not how we *build* her. |
| Root `AGENTS.md` | Stop conditions for **hosts of the catalog**. Wrong file for coding agents (OpenAI/AAIF `AGENTS.md` is a README for workers). |
| Slice log + one-sentence commits | Anthropic-style contracts, informal. |
| Tests on disk | Evaluator exists. **No CI.** Workers can claim green on a laptop. |
| `decor-board-intake`, `spec_saved` / `spec_approved` | Run-side seed. AI Config is model-only. |
| Host-only Approve | Product gate. Factory equivalent: human merge, no `--no-verify`, no force-push `main`. |

## The line (Factory.ai stages, with LD’s run layer)

```
signal → triage → spec contract → build → test → review → flag → merge
                                                              ↓
                         run: expose by policy → measure spec_approved
                              → reverse this change → cleanup the flag
                                                              ↓
                         new signal
```

## Phases — one slice each, ship in this order

### Phase 0 — Name the two agents

**Decision.** Decora (catalog host) and the factory worker (coding agent) do not share one instruction file.

**Build.** Keep host stop conditions where goose already loads them (`recipes/furnish-a-room.yaml` plus a host file if needed). Put **repo-worker** instructions in root `AGENTS.md` in the [agents.md](https://agents.md/) sense: venv, which tests, commit rule, “do not invent SKUs in fixtures,” “do not mix backlog into this PR.”

**Done when.** A Cursor/Codex session on a Python file reads how to test, not how to furnish a living room.

### Phase 1 — Make “done” mechanical

**Decision.** There is no factory without a stop the worker cannot talk past. We have tests and no pipeline.

**Build.** CI on `main` / PRs: `test_catalog.py`, `test_store.py`, `test_mcp_catalog.py`, `test_mcp_project.py`, `test_harness.py`, Studio HTTP tests that do not need a live model. Fail the job if any fail.

**Done when.** A PR that breaks `search_catalog` cannot be merged by a cheerful commit message.

### Phase 2 — One job, one contract, one flag

**Decision.** Do not start with “add PIM rows” as the signature factory demo. Start with a **load-bearing Decora behavior** you can eval both ways, and ship it behind a flag so the unit of reversal is the change.

**First job (recommended).** Something already true of the product: e.g. “Approve locks the shopping list” or “named SKUs must appear in this turn’s `search_catalog`.” Contract: files, white-box test, black-box Studio or HTTP test, flag key, default off in production until guarded rollout.

**Not the first job.** A generic “fix whatever is in the backlog” agent. That is a birdhouse.

**Done when.** A worker can take the contract, open a PR, CI green, change dark behind a flag, you flip exposure without a second deploy.

### Phase 3 — Review with criteria

**Decision.** Specialist checks, binary.

- Every SKU string in the diff exists in `app/pim/catalog.json` (or is a test fixture marked as such).
- MCP `tools/list` still matches the server module.
- No `approve` tool added.

**Done when.** Those checks run on the PR. A generic “LGTM” bot is a fail.

### Phase 4 — Run side (do not defer)

**Decision.** Match LD’s five run requirements, sized to Decora:

| Requirement | Decora |
| --- | --- |
| Know what shipped | Flag key + app version on the Studio request, not “we deployed main.” |
| Record that outlasts the incident | Flag change history (LD) plus `spec_approved` / `spec_saved` events. |
| Exposure by policy | Default: new factory-shipped behavior is flagged; guarded rollout; do not 100% a worker PR on merge. |
| Reverse one change | Kill the flag. Do not revert a deploy that also carried catalog photos. |
| Cleanup | Lifecycle: flag proven → PR to remove the branch. Agents create flags; something has to delete them. |

Wire `spec_approved` (and chat/Studio error rate) as the metrics that can stop a rollout. AI Config stays **model only**. A factory PR that rewrites `AGENT_SYSTEM_PROMPT` via LD is a regression.

**Done when.** You can ship a worker change to a slice of Studio traffic and roll **that change** back from the flag, not from git.

### Phase 5 — Signals in

**Decision.** The factory eats Decora failures, not vibes.

Seed the board from: CI red, SKU-honesty miss, Studio walk script fail, budget over cap with Keep lines dropped. One ticket = one contract from Phase 2. Production “agents fix latency” waits until Phase 4 is boring.

**Done when.** You can point at a real Decora miss last week and show the ticket → PR → flag → measure loop without a new chat designing the architecture.

## What we are abandoning from the first factory note

- **PIM-row recipe as move #1.** Inventory work is real, but it does not teach run-side control and it invites inventing SKUs. It becomes a job type after CI and flags exist.
- **Build-side-only factory.** Tests without flags is the diagram LD says everyone forgets to finish.
- **One mega-agent on the repo.** One contract per job.
- **Treating goose-as-host as factory work.** Goose proved the environment. Workers who *commit* are the factory.

## Out of scope for this plan

Anything that is not shipping Decora the design product (new catalog behavior, Studio, harness, host Approve). Runtime control of *other* agent products stays off this list.

## Suggested first three PRs

1. Split host vs worker instructions (`AGENTS.md` for workers).
2. GitHub Actions (or equivalent) running the no-key test suite on every PR.
3. One flagged Decora behavior with a contract + CI + off-by-default flag, then a guarded rollout using `spec_approved` as the metric you already emit.
