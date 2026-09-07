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

## Slice: design project as an MCP resource

**Why `project://{context_key}` is a resource, not a tool.** The host should be able to load the current job *without* asking the model to “please fetch state.” That is `resources/read`. The model may still *change* the project through tools. Read = application-controlled. Write = model-controlled, with human gates later.

**The new block** in [`mcp_servers/decor_design.py`](../mcp_servers/decor_design.py): `@server.resource("project://{context_key}")` calls `store.snapshot`. Empty keys create an intake project. Inspector can open `project://demo` with no Claude.

## Slice: update_project MCP tool

**Write vs read.** `project://` is observe. `update_project` is act. The model may set a brief, budget, room, or add a catalog SKU. It cannot mark items `committed`. That stays on `approve` in the store, which we have not hung on a tool yet.

**The tool body** is a thin switch on `action`. Every successful call returns `store.snapshot` so the host sees the new world in the `tools/call` result. `add_spec` still fails on unknown SKUs — the error travels over MCP as JSON, not as a Python exception in the host.

## Slice: request_approval MCP tool

**Human gate.** MCP says mutating work may need consent. `request_approval` is the model saying “I am done; a person must commit this.” It sets `pending_approval`. It does **not** flip drafts to committed. `store.approve` stays off the model’s tool list on purpose. The host UI will call approve. If we exposed approve as a tool, the model could commit spend by itself.

## Slice: plan_room MCP prompt

**Prompts are user-controlled.** A prompt is not Decora’s system prompt in `app/prompts.py`. The user (or a slash command) asks for `plan_room` with arguments. `prompts/get` returns the message template. The host may then send that to the model.

If we stuffed this into `AGENT_SYSTEM_PROMPT`, every request would be “plan a room.” A greeting would still trigger the whole job. MCP keeps “start this kind of job” as an explicit user move.

Inspector: Prompts → `plan_room` → fill room + budget. No chat app required. That is the Phase 1 success check.

## Slice: ignore extra env keys

Local `.env` still has Temporal-era keys. Settings used to crash on unknown fields. `extra="ignore"` lets the host boot without pulling Temporal code. Not an AAIF idea — just so the next slice can call `get_settings()`.

## Slice: MCP harness (the host loop)

**This is the agent.** The model does not import `app.catalog`. It sees tool *schemas* from `tools/list`. When it picks a tool, the harness does `tools/call`. That is the same JSON-RPC Inspector uses.

**What each block in [`app/harness.py`](../app/harness.py) does**

- `bindings_from_mcp_tools` — maps MCP `Tool` objects to Claude `bind_tools` schemas. Discovery, not a hardcoded Python list.
- `inject_context_key` — the model might forget `context_key`. The host owns the session and fills it in for mutating tools.
- `_read_project` — `resources/read` `project://{context_key}` every turn. Observe before act.
- `_run` loop — invoke Claude → if tool calls, `client.call_tool` → append `ToolMessage` → stop on `request_approval` or no more calls. Max 6 iterations.
- `Client(server)` — in-memory transport. Still MCP. Not `ToolNode(get_tools())`.

[`app/graph.py`](../app/graph.py) still has the old specialist graph. The host does not use it yet. Next slice points `/api/chat` here.

**What would still be a wrapper.** Binding LangChain `@tool` functions that call `search_products` directly. Same loop, no protocol, goose cannot share the environment.

## Slice: chat HTTP face uses the harness

[`server.py`](../server.py) `/api/chat` now calls `app.harness.run_agent`, not `app.graph.run_agent`. The response includes `project` — the same JSON as `project://{context_key}`.

Host-only routes (the model cannot call these):

- `GET /api/project` — `resources/read` equivalent for the UI
- `POST /api/project/approve` — `store.approve` (commits drafts)
- `POST /api/project/reject` — records why and clears the gate

That is human consent. `request_approval` is the ask. These routes are the answer.

## Slice: project panel in the chat UI

The right-hand panel is a *view of `project://`*, not a second chat. After each `/api/chat` the browser renders `payload.project`. Approve / Reject hit the host routes that call `store.approve` / `store.reject`. The model never sees those buttons as tools.

If this panel only showed the last assistant paragraph, we would be back to a wrapper. The artifact is the spec list.

## Slice: harness uses the host event loop

**The bug.** `anyio.run()` starts an event loop. FastAPI / uvicorn already has one. `/api/chat` is `async` and called `run_agent()`, which called `anyio.run(_run)`. Python refused: `Already running asyncio in this thread`. The UI showed a generic 500. Inspector and `python test_harness.py` still worked — those start their own loop.

**The split.** `run_agent_async` is what the host awaits. `run_agent` stays a sync wrapper for tests. The protocol did not change. Same `tools/list` / `tools/call` / `resources/read`. Only who owns the loop.

**What would still be a wrapper.** Catching the RuntimeError and retrying in a thread. That hides the host/client relationship. The host *is* the loop.

## Slice: project panel is a card beside chat

The first project-panel markup shipped, but the stylesheet the browser already had cached was the old single-column chat CSS. `.workspace` and `.project-panel` never applied, so `project://` rendered as bare headings under the chat card. That made the resource look like leftover page copy instead of the job.

Cache-bust `styles.css` and give the panel the same card treatment as chat. Side-by-side on a wide window; stacked cards on a narrow one. Still a view of `project://`, not a second transcript.

## Slice: Anthropic workspace header

**Not Claude Code.** The 500 after the loop fix was the browser hitting `/api/chat`. The host reached Claude. Anthropic returned 400: the API key is not scoped to a workspace, so the request must send `anthropic-workspace-id`.

`.env` already had `ANTHROPIC_WORKSPACE_ID`. Settings used `extra="ignore"`, so the host never read it, and `ChatAnthropic` never sent the header. Org keys need that header. Personal scoped keys do not.

[`app/llm.py`](../app/llm.py) `workspace_headers` attaches it when the setting is non-empty. MCP did not change. This is how the host talks to the model, not how it talks to `decor-design`.

## Slice: default model is Claude Sonnet 5

LaunchDarkly `decor-agent-main` was already `Anthropic.claude-sonnet-5`. That ID is current (retirement not sooner than June 2027). The host fallback was still `claude-sonnet-4-20250514`, a May 2025 snapshot.

Sonnet 5 rejects non-default `temperature` and turns adaptive thinking on unless you disable it. The client omits sampling and sets `thinking: disabled` so a 1024-token tool loop is not eaten by hidden reasoning. MCP tools and resources did not change.

## Slice: host job prompt beats the LaunchDarkly wrapper

A living-room job came back as invented IKEA Kivik / Article Sven prices. The catalog already has `IKE-SOFA-KL1` and `ART-SOFA-721`. The model said inventory was empty and wrote a shopping list from weights.

**Why.** `get_completion_config("decor-agent-main")` still returns the old specialist-router system prompt (`style_advisor`, name Benjamin Moore from memory, budget-conscious IKEA/Target/Wayfair). The host bound MCP tools, then handed the model instructions that describe tools that do not exist. That is a wrapper wearing a `tools/list`.

**What we did.** The harness always uses [`AGENT_SYSTEM_PROMPT`](../app/prompts.py). LaunchDarkly still picks the model. It does not get to write the job. A free/premium line may prefer cheaper or pricier *catalog* rows. It may not invent brands.

Updating the LaunchDarkly messages is later. Until then the host owns the job.

## Slice: chat text from tool-call turns

The UI showed "No response returned." `/api/chat` was 200. `response` was `""`. The browser treats an empty string as missing.

**Cause.** `_final_text` skipped any `AIMessage` that also had `tool_calls`. A live Sonnet 5 turn is mixed: a short preamble plus `update_project` / `search_catalog`. That preamble was thrown away. If the loop then stopped on `request_approval` or `max_iterations`, there was no later text-only message. The host returned silence. The project panel can still be empty on that same turn if `update_project` omitted `room_name` or `budget_dollars` — that is a separate miss.

**Fix.** Read text blocks even on tool-call turns. If there is still no text, the host writes one sentence from `project://` (real SKUs only).

## Slice: host writes project:// when the model only talks

The chat named Sven / Seno / Arca. The side panel stayed Intake. `renderProject` only reads `payload.project`. Chat text is not the database.

She had searched the catalog, then answered from those rows, and skipped a successful `update_project` (or called it without `room_name` / `budget_dollars`). The resource never changed.

The host now fills omitted job facts on `tools/call`, then always persists budget, room, brief, and named catalog rows over MCP. The panel also refetches `GET /api/project` so it reads the resource, not only the chat payload.

Catalog-only is the default job. The user should not have to say "use SKUs only."

## Slice: catalog search folds hyphens

A brief like "12x14 living room midcentury $2000" used to miss `ART-SOFA-721` because the row says `mid-century` and `12x14` is not a product field. Search now folds hyphens (`midcentury` = `mid-century`) and drops dimensions and stopwords. Still no invented rows. Empty result means empty inventory.
