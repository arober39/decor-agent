1. Set up the environments
docker-compose.yml: Qdrant local-test and shared-dev, separate volumes, distinct API keys (full + read-only where Qdrant allows). Socat (or similar) tunnel so shared-dev appears on a local-looking port next to local-test. environments.yaml maps every host:port — including the tunnel — to a name and sensitivity. Tag the tunnel shared.

2. Build ingestion
Local sentence-transformers model. Embed catalog text (name, description, style, materials, colors). Create a Qdrant collection with that vector size; payload includes SKU, price, category. Target environment is a required argument, never a silent default.

3. Upgrade search_catalog
Embed the query, retrieve from Qdrant, apply budget/category/avoid filters. Keyword search stays as fallback. Small labeled-query tests. MCP server stays model-free.

4. Point Decora at shared-dev
The running app reads shared-dev (via the tunnel or the shared port you choose). That is the environment worth protecting.

5. Lock down permissions
Agent default key is read-only on shared-dev. Full-access key stays out of the agent session. Tunnel/shared connections stay out of the agent working session unless you deliberately include them for a scenario.

6. Inventory tools and targets
List every tool/command the agent can run. Tag each as read-only, write, or destructive. Tag each target local or shared in environments.yaml.

7. Build the reproduction scenario
Seed local-test with a broken collection (wrong vector size). Script: read-only query on the tunnel port, then “fix the schema.” Run once with no guardrails and record the baseline.

8. Set up LaunchDarkly
Project with local and shared environments. Policy flag (JSON): mode off / shadow / live; per-environment action (allow / confirm / block) for destructive work; fallback behavior. Rule: destructive + shared always requires human confirmation. In-code fallback is the strictest policy (fail closed). Store Jev model id, question text, and thresholds as config (flag custom params and/or an AI Config used as a config bag — not as “agent mode Jev”).

9. Confirm Jev access in the app’s contract
Pin jev-1.13.0 in that config. Key already works; do not call Jev from Decora until step 13. Add TYPESAFE_API_KEY to .env.example if it is not there yet.

10. Define the Jev questions (in LaunchDarkly config, not hardcoded forever)
Nouls: is this destructive? could the target be shared/non-local? does the target match stated intent?
Choice: proceed / confirm_with_human / block.
Ask them in one request over the same state. Code still owns the final allow/confirm/block using policy + Noul/Choice values. A Noul near 0.5 is uncertainty.

11. Build the state for each check
Named JSON fields: exact command, resolved target, stated intent, recent session history (especially prior uses of that target), matching environments.yaml entries.

12. Add the deterministic check and pre-tool-call hook
Standalone Python module: resolve target → look up registry → read policy flag. Hook it in the agent that runs the scenario (and keep it reusable for Decora’s harness). Agent-independent. This layer does not call Jev.

13. Add the Jev check
Interface + stub first, then typesafe-sdk against jev-1.13.0. Load questions/threshold/model id from LaunchDarkly at runtime. Log the model field from the response.

14. Build the human confirmation step
Show command, resolved target, Jev scores. Require explicit approval of the target, not only the action. Log who approved and when. Host-only; the model still cannot call approve.

15. Wire up telemetry
Every check writes one decision: command, resolved environment, deterministic decision, Jev model/nouls/suggested, outcome, disagreement. Source of record is LaunchDarkly: custom metrics (`flinch_check`, `flinch_block`, `flinch_escalate`, `flinch_override`) plus Observability (`observe.record_log` / span `flinch.check`, service `decor-agent`). JSONL under `logs/` is a local backup for the post screenshot, gitignored. Flush the SDK and OTLP exporters when the repro process exits. Observability plugin: `launchdarkly-observability`, `instrument_logging=False` so structlog format stays local; the OTEL log handler is still attached. Set `ldobserve.observe` to DEBUG — the plugin never does, so `record_log(..., INFO)` was dropped by the stdlib WARNING default while traces still exported. Leave library auto-instrumentation on. Skip only `qdrant_client`. In the UI, Logs must use **production** (same as the SDK key). Search `flinch.decision`. The JS/Test install card means zero logs have been ingested yet.

16. Roll out gradually
Policy **shadow** is control; **live** is treatment. Do this as a LaunchDarkly **guarded rollout** on `flinch-policy` in production (not a one-shot fallthrough flip). Variations already exist: `shadow` (mode shadow, shared confirm) and `live` (mode live, shared confirm). Off variation stays fail-closed. In Targeting: default rule → Serve → Guarded rollout. Control = shadow, treatment = live. Target by `user`. Stages cannot exceed 50% each; after the last healthy stage LD promotes to 100%. Demo windows: 10% for 15 minutes, then 50% for 15 minutes. Metrics: `flinch-escalate` and `flinch-block` (rollback + notify, ~20% regression), `flinch-override` (notify). Repro always used `flinch-baseline`; pass `--context-key other-user` to land in another bucket and compare `enforce` false vs true. Do not `--execute`. Compare Observe logs + those metrics, then let the rollout complete.

17. Add the fallback
If Jev is down or rate-limited: human confirmation for destructive or shared-target actions; read-only continues. Fallback mode comes from the policy flag, which works without Jev.

18. Test against the real failure
Rerun the scenario with each layer on. Record which layer caught what in Observability (filter `flinch.decision` / service `decor-agent`) and keep the repro as a regression test for the post.