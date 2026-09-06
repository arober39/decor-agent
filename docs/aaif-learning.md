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

## Slice: catalog search as an MCP tool

**The protocol idea.** A *tool* is model-controlled. The host advertises it via `tools/list`. The model picks it. The host (or test client) executes `tools/call`. The server runs code and returns content. Claude never imported `search_products`.

**What each block does**

- [`mcp_servers/decor_design.py`](../mcp_servers/decor_design.py) `MCPServer(...)` — names this environment `decor-design`. `instructions` is what a host may show the model about the *server*, not Decora’s personality.
- `@server.tool()` `search_catalog` — the SDK turns the type hints and docstring into the JSON Schema that `tools/list` returns. The body only calls `search_products`. No LLM.
- `if __name__ == "__main__"` `server.run(transport="stdio")` — Inspector and goose can spawn this as a subprocess. JSON-RPC on stdin/stdout.
- [`test_mcp_catalog.py`](../test_mcp_catalog.py) `Client(server)` — in-memory MCP client. Same messages as stdio, no subprocess. If this test passes, the wire protocol works.

**How this differs from `style_advisor`.** That file was `@tool` from LangChain plus `llm.invoke`. This file never thinks. It looks up inventory.

Try it yourself later: `npx @modelcontextprotocol/inspector python mcp_servers/decor_design.py` and call `search_catalog`.

## Slice: catalog product as an MCP resource

**Tools vs resources.** A tool is something the *model* decides to run. A resource is something the *application* can fetch and attach as context. `search_catalog` is “find me candidates.” `catalog://sku/{sku}` is “here is the record for this SKU.” Same inventory, different primitive, different who-decides.

**What the new block does**

- `@server.resource("catalog://sku/{sku}")` — the `{sku}` makes this a *template* resource. `resources/templates/list` advertises it. `resources/read` with `catalog://sku/ART-SOFA-721` runs `catalog_sku("ART-SOFA-721")`.
- Return type `dict` — the SDK JSON-encodes it. The test reads `resource.contents[0].text`.
- Unknown SKU — we still return a JSON error body. The resource exists; the product does not. That is more honest than a 404-shaped crash if a host prefetches a hallucinated SKU.

The test in [`test_mcp_catalog.py`](../test_mcp_catalog.py) now does `call_tool` then `read_resource` for the first hit. Two protocol methods, one catalog.

## Slice: in-memory design project

**Why a store before `project://`.** Same lesson as the catalog. A resource has to read something real. Chat history is not a home. [`app/project.py`](../app/project.py) is the document (brief, rooms, spec list, budget, approval). [`app/store.py`](../app/store.py) is the filing cabinet keyed by `context_key`.

**What each type is**

- `Room` / `Brief` — intake facts the designer owns.
- `SpecItem` — a catalog row *on this job*. `draft` until a human approves. `committed` is irreversible from the model’s point of view.
- `DesignProject.as_public_dict()` — the JSON a `project://` resource will return. No photo bytes, no internals.

`add_spec` calls `get_product`. Unknown SKUs raise. The world still refuses hallucinations before MCP wraps it.
