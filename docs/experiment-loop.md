# Experiment loop on Decora (main)

Clone of the AWS + LaunchDarkly experimentation lifecycle, pointed at **this** product — not the Temporal chat wrapper.

Source pattern: [Automating the experimentation lifecycle](https://aws.amazon.com/blogs/devops/automating-the-experimentation-lifecycle-with-kiro-aws-devops-agent-and-launchdarkly/).

## What we measure

Primary KPI: **approved spec lines** (`spec_approved` count), not tokens.

Secondary: **saved spec lines** (`spec_saved`). A skip is not a save.

Guardrail: error rate / failed `/api/chat` and `/api/project/from-board`. Never the primary KPI.

Goal example: **+15% approved spec lines** on board-first vs text-only.

## Treatment

| Variation | What the user gets |
| --- | --- |
| Control | Starter chips + text brief. `decor-board-intake` off. |
| Treatment | Same job, plus **Map sample board**. Flag on. |

Both write the same `project://`. Both require host Approve. The experiment is intake shape, not a new agent.

## LaunchDarkly the agent way

1. Boolean flag `decor-board-intake` on the **product**, default on locally.
2. Custom events `spec_saved` and `spec_approved` from the store (not from the model).
3. AI Config `decor-agent-main` = **model only**. Do not let LD rewrite `AGENT_SYSTEM_PROMPT`.

Until an Experiment MCP / Guardian can deploy this repo:

- Run the experiment at **10% traffic, fixed 50/50**.
- After a win, ramp **by hand** (20 → 30 → 40). Do not treat a Guarded Release ramp as the experiment.
- Lose → archive the flag, iterate the board mapping or the copy. Rollback is flag state, not a redeploy.

## Skill the orchestrator should follow

When an Experiment MCP exists and can merge + deploy `main`:

1. **Plan** — metric = approved spec lines; guardrail = error rate; treatment = board intake.
2. **Prove** — 10% of traffic, 50/50, no ramp during the test.
3. **Decide** — win: start a Guarded Release (or a manual ramp). Lose: archive, change one variable, new flag.
4. **Do not** use tokens or “smarter model” as the success metric for this loop.

Constraints live in server code (`get_flag`, store events), not in a system prompt.
