# Decor Agent

A production-grade LangGraph agent that gives confident, specific interior design advice. Built to demonstrate the LaunchDarkly AI iteration loop — AI Configs for runtime-managed prompts and models, progressive release, online evals, and observability.

![Decor Agent landing page mockup](docs/hero.png)

## What it does

Users ask Decora, a senior interior design advisor, about colors, layouts, and trends. The agent routes each question to one of three specialist tools, synthesizes a short opinionated response, and returns it alongside rich metadata for observability.

Example questions:

- "What paint color works with dark oak floors?" → `style_advisor`
- "I have a 12x14 living room with a $2000 budget" → `room_planner`
- "Is terrazzo still trending?" → `trend_spotter`
- "How do I make a small bathroom feel bigger?" → `room_planner`
- "Hello!" → direct response, no tool call

## Architecture

```
START
  ↓
input_guard        (length / PII / empty checks — deterministic)
  ↓
agent              (Claude with bound tools — picks a tool or responds directly)
  ↓
execute_tools      (ToolNode runs the selected tool, which makes its own specialist LLM call)
  ↓
error_handler      (bounded retry up to max_retries, then graceful fallback)
  ↓
agent              (loops back to synthesize the tool result)
  ↓
response_formatter (builds metadata sidecar: routed_to, tool_calls_made, tokens, latency)
  ↓
END
```

Each node is a checkpoint boundary, so a failure in `execute_tools` resumes from there on retry, not from the start.

## Project layout

```
decor-agent/
├── app/
│   ├── config.py              # Pydantic-settings singleton
│   ├── logging.py             # structlog (JSON prod / console dev)
│   ├── state.py               # AgentState + metadata merge reducer
│   ├── prompts.py             # Four structured system prompts
│   ├── flags.py               # LaunchDarkly integration (pending)
│   ├── graph.py               # Graph definition + run_agent()
│   ├── nodes/
│   │   ├── input_guard.py
│   │   ├── agent.py
│   │   ├── error_handler.py
│   │   └── response_formatter.py
│   └── tools/
│       ├── style_advisor.py
│       ├── room_planner.py
│       └── trend_spotter.py
├── server.py                  # FastAPI — /api/chat, /api/health, static /web
├── test_agent.py              # 13-case end-to-end suite
├── generate_traffic.py        # Load generator (pending)
├── web/                       # Static frontend
├── docs/                      # README assets
├── requirements.txt
└── .env.example
```

## Quickstart

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env           # then edit to add ANTHROPIC_API_KEY
python server.py               # starts on http://localhost:8000
```

Open `http://localhost:8000/docs` for the interactive Swagger UI, or hit the API directly:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "What color goes with walnut floors?"}'
```

## Run the test suite

```bash
LOG_LEVEL=WARNING python test_agent.py
```

Current status: **13 / 13 passing** across routing, guard, off-topic, and edge cases.

## Environment

| Variable | Default | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | _required_ | Claude API key |
| `LD_SDK_KEY` | `""` | LaunchDarkly server SDK key (used once `flags.py` is wired) |
| `LOG_LEVEL` | `INFO` | structlog level |
| `ENVIRONMENT` | `development` | Switches log format between console and JSON |

## Production hygiene

- **Input validation** at two layers — Pydantic on the HTTP boundary, `input_guard` inside the graph
- **Bounded retries** — `max_retries=2`, then a graceful fallback message
- **Structured logs** on every step: `input_guard.pass`, `agent.invoke`, `tool.invoke/success/error`, `error_handler.retry/exhausted`, `http.request`
- **Metadata sidecar** on every response: `routed_to`, `tool_calls_made`, token usage, per-node latency, error counts — ready to feed evals and analytics
- **Errors never leak** to the client; full tracebacks go to logs only
- **Request IDs** honored from `x-request-id` header or generated per request

## Tech stack

Python 3.12 · LangGraph · LangChain · Anthropic Claude Sonnet 4 · FastAPI · Pydantic · structlog · LaunchDarkly (server SDK + AI SDK, pending)

## What's deferred

- `app/flags.py` — LaunchDarkly SDK + AI Configs integration (model, prompt, params managed at runtime via flags)
- `generate_traffic.py` — load generator to produce monitoring data for LD dashboards
- **Cached LLM client factory** — lands with the AI Configs work, since the cache key depends on flag-controlled fields
