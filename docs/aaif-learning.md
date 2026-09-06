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

## Slice: official MCP Python SDK

**Why this package, not LangChain tools.** MCP is an AAIF standard. LangChain `@tool` is a vendor helper that binds a Python function to one model call. The official [`mcp`](https://py.sdk.modelcontextprotocol.io/) SDK (v2, `MCPServer`) speaks JSON-RPC: `tools/list`, `tools/call`, `resources/read`, `prompts/get`. Goose, Claude Desktop, and our future Decora host all speak that protocol. One environment, many agents.

**What we did not add yet.** No server, no tools. A dependency with no server would be cargo-culting. The next slice creates a catalog (the world). The slice after that exposes it over MCP.

Pinned `mcp>=2.1.1` in [`requirements.txt`](../requirements.txt). Use `MCPServer` — the old docs name `FastMCP` was renamed in v2.

## Slice: seeded catalog (no LLM)

**Why a catalog before an MCP server.** MCP exposes an environment. If we skip this and let Claude invent “West Elm Andes sofas,” the protocol is a socket around a hallucination. The world has to exist first.

**What each piece does**

- `Product` in [`app/catalog.py`](../app/catalog.py) — one real row: sku, brand, category, room, price in cents, tags. Frozen so nothing mutates inventory by accident.
- `PRODUCTS` — the inventory. If it is not in this tuple, it does not exist.
- `get_product(sku)` — lookup. Returns `None` for fakes. That `None` is the point.
- `search_products(...)` — keyword + filters. This is what a `search_catalog` MCP *tool* will call later. Today it is just a function.

**What this is not.** Not a tool. Not a prompt. Not an agent. A module goose or Decora will both use once we hang it on MCP.
