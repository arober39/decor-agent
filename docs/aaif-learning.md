# Learning log: Decora as an AAIF agent

This file is a running explanation of *why* each slice exists. Read it in order. Chat will repeat the same ideas with more walkthrough when a slice lands.

We are learning the [Agentic AI Foundation](https://aaif.io/) stack by rebuilding this familiar interior-design app. Build order is a dependency chain: **MCP server → (optional) goose as a consumer → Decora harness → AGENTS.md → A2A → agentgateway → LaunchDarkly**.

## Slice: start from the Q&A wrapper

**Commit idea:** record the starting point after throwing away the in-process “project agent” and refusing Temporal.

**What was wrong with the last attempt.** We added a catalog, a `DesignProject` store, and LangChain `@tool` functions, then looped them in LangGraph. That is a better chatbot. It is not MCP. Tools still lived in the same process as the model. `ToolNode` called Python functions. No other agent (goose, Claude Desktop, a future retailer) could use that environment.

**What was wrong with Temporal on `origin/main`.** Temporal makes a *workflow* durable (crash, wait, resume). AAIF’s first standard is how an agent *acts on an environment*. Durable execution is an operations concern we are not learning yet. Local `main` was 8 commits behind those Temporal files. We did not pull them. This work lives on `aaif-mcp-agent`.

**What you have right now.** The original Decor Agent:

- [`app/graph.py`](../app/graph.py) — `input_guard → agent → execute_tools → error_handler → agent → formatter`
- [`app/tools/style_advisor.py`](../app/tools/style_advisor.py) (and room/trend) — each “tool” is another Claude call with a specialist system prompt
- No durable home, no real SKUs, no protocol

That is the before picture. Next slices put a world *outside* the model and talk to it with MCP.
