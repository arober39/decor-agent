# When Your API Call Takes Five Minutes: An Operations Playbook for Long-Running LLM Endpoints

**Conference:** API World 2026 — API operations track
**Status:** CFP accepted (tracked in [DEVREL-1240](https://launchdarkly.atlassian.net/browse/DEVREL-1240))
**Demo repo:** this project (decor-agent)
**Slides:** [Google Slides](https://docs.google.com/presentation/d/1wY9MWtNY10n6h-kFuoQoeh-DqdpwlPK_VbWExSertzE/edit?usp=sharing)

## Abstract

REST was designed for sub-second, stateless, deterministic calls. LLM endpoints break every one of those assumptions. A single user request can take five minutes. The output is non-deterministic, so retries don't mean what they used to. Models and prompts change weekly, but your deploy cycle doesn't. Workers crash mid-request, clients time out, and idempotency keys quietly stop protecting you. The operational patterns that kept your CRUD APIs reliable silently fail under LLM workloads.

This talk is about what it actually takes to operate an LLM-backed API in production once you accept that it isn't really an API anymore — it's a workflow with an HTTP face. I'll walk through a working example: a design assistant that takes a budget and generates a whole-home furnishing plan, fanning out per-room work across minutes. Mid-talk, I'll kill the worker on stage and show why the user never notices. You'll leave with a concrete operational playbook — endpoint shapes, durable execution, runtime config control, and the observability that ties them together.
