# Ship, Observe, Iterate, Reship: Running an AI Agent Without Redeploys

Most teams shipping LLM features today have a problem that looks small on day one and ugly by month three: every meaningful change — a prompt tweak, a model swap, a new persona for premium users — lives inside the codebase. That means every tweak is a PR, a review, a build, a deploy, and whatever flakiness your CI pipeline brings along for the ride. It works, but it scales poorly, and it forces the wrong people to be in the loop. Product managers wait on engineers to edit copy. Applied researchers can't test a new model without shipping code. A regression lands and there's no way to roll back short of reverting the commit.

This post walks through an alternative pattern we've been demoing with a small interior-design agent called Decor Agent, using LaunchDarkly as the control plane. The goal isn't to sell you on any particular tool — it's to make the pattern concrete. Once you see it laid out, it's hard to un-see.

## The setup

Decor Agent is a LangGraph-ish Python service with four prompts inside it: a main orchestrator that decides how to route an incoming question, and three specialist tools — a style advisor, a room planner, and a trend spotter. Each tool is a system prompt plus a model call. The orchestrator reads a user's message, picks the right specialist, and returns an opinionated recommendation like "walnut floors want warm whites, try Benjamin Moore White Dove."

On day zero of the demo, the prompts are hardcoded in `app/prompts.py` and every tool instantiates its own `ChatAnthropic` client with a model string baked in. It works perfectly well until the first time someone asks you to change anything.

The refactor we're about to do pulls those prompts out of code and into LaunchDarkly's AI Configs — which are basically structured, versioned, targetable prompt+model bundles — and then uses feature flags, metrics, and LLM-as-judge evaluators to turn prompt editing into a grown-up release pipeline.

## Start with a kill switch

The first thing to build is the least glamorous: a boolean flag called `decor-agent-enabled` that wraps the whole chat endpoint. Off means the endpoint returns a friendly maintenance message, on means traffic flows normally. That's it.

Kill switches get undersold because they sound trivial, but they're the single most important primitive in any AI feature. When your LLM provider has an outage, when a prompt change accidentally starts leaking PII into responses, when you ship a regression nobody caught — you want one toggle, one click, and the bad behavior is gone. No redeploy. No frantic `git revert`. Just off.

The flag sits in front of the agent in about six lines of code and it earns its keep the first time anything goes sideways.

## Move prompts into configuration

The real unlock starts in phase two. Every prompt that used to be a Python constant moves into an AI Config — one for the main agent, one for each specialist tool. The initial variation for each is a verbatim copy of the current prompt, so nothing behaves differently on day one. But now a product manager can open the LaunchDarkly UI, edit the style advisor's system prompt to say "prefer IKEA and Article over designer brands," hit save, and the next request returns a fundamentally different answer. No PR. No deploy. No engineer involvement after the initial wiring.

The code-side work here is small but important. Every tool that used to do `ChatAnthropic(model="...", system_prompt=...)` now does something like:

```python
cfg = get_completion_config("decor-style-advisor", context, default)
llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature)
response = llm.invoke([SystemMessage(cfg.system_prompt), HumanMessage(user_question)])
cfg.track_success()
cfg.track_tokens(usage.input_tokens, usage.output_tokens)
```

The `cfg` object is a thin wrapper that knows where it came from — LaunchDarkly at runtime, or a local fallback when the SDK key isn't set. Local development and unit tests keep working in offline mode against the original hardcoded prompts, which is non-negotiable if you want your team to actually adopt the pattern.

## Give different users different agents

Once prompts are configuration, variations become the next obvious move. On the main agent config, you create two variations alongside the baseline: `budget-conscious` (leads with IKEA, Target, Wayfair, names price tiers, flags splurges) and `luxury-curator` (Design Within Reach, unlacquered brass, named designers, skips mass-market references entirely). Then you attach a targeting rule that routes free-tier users to the first and premium users to the second.

The demo moment here is genuinely satisfying. Ask the agent "help me pick a sofa, budget-friendly but stylish" as a free user and you get Article recommendations with prices attached. Ask the exact same question as a premium user, and you get a Pinch London sofa in mohair velvet with a clear note on lead times. Same code path, same message, two valid answers, priced appropriately to the audience.

This is also where you can start swapping models per task rather than globally. Style advice is creative and forgiving — it's a reasonable place to serve Haiku and save two-thirds of the per-request cost. Room planning needs to reason about square footage and clearances, so it stays on Sonnet. The agent doesn't know or care; it just reads `cfg.model` from each config and routes accordingly.

## Prove it's safe before you ship it

Prompt changes regress silently. That's the quiet danger. Unit tests catch routing bugs and API breakage, but they can't catch "this new prompt now consistently blows the user's budget on recommendations." For that you need evals.

LaunchDarkly's LLM Playground handles the offline side. You upload a labeled dataset of maybe thirty design questions — some budget-constrained, some splurge-friendly, some with expected outputs for accuracy checks — and attach a few criteria: factuality, relevance, budget adherence. Run it against two variations and you get a side-by-side scorecard. When `luxury-curator` scores 0.41 on budget adherence against `budget-conscious`'s 0.92, you have quantitative evidence that your targeting rule is doing real work, and more importantly, you've caught the regression before a single production user saw it.

Offline evals are the seatbelt. Online evals are the airbag.

## Ship it gradually, revert automatically

New variation, proven safe against the dataset, ready to roll out. Guarded rollouts handle the rest: 10% for thirty minutes, then 25%, then 50%, then 100%, with auto-rollback if error rate, p95 latency, or fallback-response rate breaches a threshold. You define the metrics, you define the limits, and LaunchDarkly watches them against the new variation's cohort in real time.

The demo version of this is satisfying to watch — you plant a broken variation halfway through the ramp, error rate spikes, and thirty seconds later the system has reverted itself with a clean audit trail. Nobody paged. No war room. The system noticed what you promised it would notice, and it did what you promised it would do.

## Catch the drift your tests can't

Offline evals score a fixed dataset. Useful, but static. Once a variation is in production you also want continuous scoring against real traffic, which is where LLM-as-judge evaluators earn their keep. Three judges we attach in the demo: one that asks "does this response commit to a concrete recommendation or does it hedge," one that asks "does this name specific products and dimensions," and — the interesting one — a `trend_still_current` judge that takes today's date as a variable and asks whether the trend claims in a response have aged poorly.

That third judge catches a failure mode offline evals structurally can't touch. The same prompt, the same model, and the same test dataset will score identically today and a year from now. Meanwhile the actual world has moved on, terrazzo is no longer having its moment, and your trend spotter is quietly serving 2023 recommendations to 2026 users. Running the judge against every production response surfaces that decay as a downward curve on a dashboard, which is exactly what you want: a measurable, dated signal that the prompt needs a refresh.

## The dashboard tells the whole story

At the end of all this you have one dashboard showing request volume split by variation, cost per variation in tokens and dollars, p50 and p95 latency per tool, judge scores trending over time, and a visible spike-then-recovery where the guarded rollout caught your planted regression. Every ramp, every rollback, every prompt edit, every model swap — all of it happened without a single redeploy.

That's the whole pattern in one sentence: ship, observe, iterate, reship, all without a redeploy. It's not a product pitch so much as an operating model for running LLM features that don't degrade silently and don't require heroics to change. You can assemble it from other pieces if you want — write your own flagging layer, wire your own metrics, build your own playground — but the shape of the thing is what matters. Configuration, not code. Targeting, not conditionals. Evals as guardrails, not aspirations. Rollouts that revert themselves.

Once your AI feature is wired this way, the entire conversation about shipping it changes. The people closest to the behavior — PMs, designers, applied researchers — are the ones making the changes. Engineers build the rails and then get out of the way. And the agent keeps getting better, one small, observable, reversible change at a time.
