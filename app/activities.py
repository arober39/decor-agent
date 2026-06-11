"""Temporal activities: every non-deterministic, side-effecting operation.
Reuses the existing llm.py factory and flags.py AI-Config resolution, so the
activities run the same domain logic as the LangGraph nodes — only the
orchestration moved to Temporal.

These are *synchronous* (`def`) activities because the underlying LLM call
(LangChain `.invoke()`) is blocking. The worker runs them in a ThreadPoolExecutor
(see app/worker.py), so the whole-home fan-out actually executes rooms in
parallel instead of blocking the event loop. See:
https://docs.temporal.io/develop/python/best-practices/python-sdk-sync-vs-async"""

import time
from dataclasses import dataclass

from langchain_core.messages import (
    AIMessage, HumanMessage, SystemMessage, ToolMessage,
)
from temporalio import activity

from app.config import get_settings
from app.flags import (
    AIConfigDefault, build_context, current_context_key,
    get_completion_config, set_current_context_key,
)
from app.llm import get_llm
from app.prompts import (
    AGENT_SYSTEM_PROMPT, ROOM_PLANNER_PROMPT,
    STYLE_ADVISOR_PROMPT, TREND_SPOTTER_PROMPT,
)
from app.tools import get_tools


# ---------------- Activity I/O (plain dataclasses → serialize into history) ----------------

@dataclass
class AgentTurnInput:
    messages: list[dict]
    context_key: str = "anonymous"

@dataclass
class AgentTurnResult:
    text: str
    tool_calls: list[dict]
    input_tokens: int
    output_tokens: int
    model: str

@dataclass
class ToolInput:
    name: str
    args: dict
    context_key: str = "anonymous"

@dataclass
class ToolResult:
    text: str
    latency_ms: float
    model_used: str

@dataclass
class ExtractRoomsInput:
    message: str
    context_key: str = "anonymous"

@dataclass
class ExtractRoomsResult:
    rooms: list[str]

@dataclass
class RoomPlanInput:
    room: str
    budget: str
    context_key: str = "anonymous"

@dataclass
class RoomPlan:
    room: str
    plan_text: str
    latency_ms: float
    model_used: str

@dataclass
class ShoppingListInput:
    approved_plans: list[dict]
    budget: str
    context_key: str = "anonymous"


# ---------------- Helpers ----------------

def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def _to_lc_messages(messages: list[dict]) -> list:
    """Rebuild LangChain message objects from the plain dicts that crossed the
    Temporal serialization boundary. LangChain message objects don't round-trip
    through Temporal's JSON converter, so we pass dicts and rehydrate here."""
    out = []
    for m in messages:
        role = m["role"]
        if role == "user":
            out.append(HumanMessage(content=m["content"]))
        elif role == "assistant":
            out.append(AIMessage(content=m.get("content", ""),
                                 tool_calls=m.get("tool_calls", [])))
        elif role == "tool":
            out.append(ToolMessage(content=m["content"],
                                   tool_call_id=m["tool_call_id"]))
    return out


def _build_user_content(name: str, args: dict) -> str:
    """Reconstruct each specialist tool's user prompt from its tool-call args,
    mirroring what your @tool functions assembled internally."""
    if name == "room_planner":
        parts = []
        dims = args.get("room_dimensions", "not specified")
        budget = args.get("budget", "not specified")
        if dims and dims != "not specified":
            parts.append(f"Room dimensions: {dims}")
        if budget and budget != "not specified":
            parts.append(f"Budget: {budget}")
        parts.append(f"Question: {args.get('question', '')}")
        return "\n\n".join(parts)
    if name == "style_advisor":
        q = args.get("question", "")
        prefs = args.get("style_preferences", "not specified")
        if prefs and prefs != "not specified":
            return f"Style preferences: {prefs}\n\nQuestion: {q}"
        return q
    return args.get("question", "")


_TOOL_PROMPTS = {
    "room_planner": ROOM_PLANNER_PROMPT,
    "style_advisor": STYLE_ADVISOR_PROMPT,
    "trend_spotter": TREND_SPOTTER_PROMPT,
}
_TOOL_CONFIG_KEYS = {
    "room_planner": "decor-room-planner",
    "style_advisor": "decor-style-advisor",
    "trend_spotter": "decor-trend-spotter",
}


def _invoke_with_fallback(system: str, user: str, primary_model: str,
                          max_tokens: int, temperature: float) -> tuple[str, str]:
    """Try the primary model; on failure fall back to a second Claude model.
    Raises only if BOTH fail, letting Temporal's RetryPolicy back off and retry
    the whole activity. This is the multi-provider-resilience demo."""
    s = get_settings()
    messages = [SystemMessage(content=system), HumanMessage(content=user)]
    candidates = [primary_model]
    if s.fallback_model and s.fallback_model != primary_model:
        candidates.append(s.fallback_model)
    last_exc = None
    for model in candidates:
        try:
            llm = get_llm(model, max_tokens, temperature)
            resp = llm.invoke(messages)
            return _extract_text(resp.content), model
        except Exception as exc:
            last_exc = exc
            activity.logger.warning(f"llm.model_failed model={model} error={exc}")
            continue
    raise RuntimeError(f"all LLM models failed: {last_exc}")


# ---------------- Activities ----------------

@activity.defn
def agent_turn(inp: AgentTurnInput) -> AgentTurnResult:
    """Claude with bound tools: route to a specialist tool or answer directly.
    Mirrors app/nodes/agent.py, including AI-Config resolution via flags.py."""
    settings = get_settings()
    set_current_context_key(inp.context_key)
    tools = get_tools(inp.context_key)
    context = build_context(inp.context_key)
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=AGENT_SYSTEM_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-agent-main", context, default)

    llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature).bind_tools(tools)
    lc_messages = [SystemMessage(content=cfg.system_prompt),
                   *_to_lc_messages(inp.messages)]

    start = time.perf_counter()
    try:
        resp = llm.invoke(lc_messages)
    except Exception:
        cfg.track_error()
        raise
    latency_ms = (time.perf_counter() - start) * 1000

    tool_calls = [{"name": tc["name"], "args": tc["args"], "id": tc["id"]}
                  for tc in (getattr(resp, "tool_calls", []) or [])]
    usage = getattr(resp, "usage_metadata", None) or {}
    cfg.track_success()
    cfg.track_duration(int(latency_ms))
    if usage:
        cfg.track_tokens(usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    return AgentTurnResult(
        text=_extract_text(resp.content),
        tool_calls=tool_calls,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        model=cfg.model,
    )


@activity.defn
def run_tool(inp: ToolInput) -> ToolResult:
    """Single specialist tool call. Resolves its own AI Config and uses the
    multi-model fallback. Replaces ToolNode + the per-tool @tool wrappers."""
    settings = get_settings()
    set_current_context_key(inp.context_key)
    context = build_context(inp.context_key)
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=_TOOL_PROMPTS[inp.name],
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config(_TOOL_CONFIG_KEYS[inp.name], context, default)

    start = time.perf_counter()
    text, model = _invoke_with_fallback(
        cfg.system_prompt, _build_user_content(inp.name, inp.args),
        cfg.model, cfg.max_tokens, cfg.temperature)
    latency_ms = (time.perf_counter() - start) * 1000
    cfg.track_success()
    cfg.track_duration(int(latency_ms))
    return ToolResult(text=text, latency_ms=latency_ms, model_used=model)


@activity.defn
def extract_rooms(inp: ExtractRoomsInput) -> ExtractRoomsResult:
    """Parse a whole-home request into a list of rooms to plan in parallel."""
    settings = get_settings()
    system = ("Extract the list of rooms the user wants planned. "
              "Return ONLY a comma-separated list, no prose. "
              "If none are named, return: living room, bedroom, kitchen")
    text, _ = _invoke_with_fallback(
        system, inp.message, settings.default_model, settings.max_tokens, 1.0)
    rooms = [r.strip() for r in text.split(",") if r.strip()]
    return ExtractRoomsResult(rooms=rooms or ["living room", "bedroom", "kitchen"])


@activity.defn
def plan_room(inp: RoomPlanInput) -> RoomPlan:
    """Plan one room. One of these runs per room, concurrently (fan-out),
    each retried independently by Temporal."""
    settings = get_settings()
    set_current_context_key(inp.context_key)
    context = build_context(inp.context_key)
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=ROOM_PLANNER_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-room-planner", context, default)

    user = f"Room: {inp.room}\nBudget: {inp.budget}\n\nPlan this room."
    start = time.perf_counter()
    text, model = _invoke_with_fallback(
        cfg.system_prompt, user, cfg.model, cfg.max_tokens, cfg.temperature)
    latency_ms = (time.perf_counter() - start) * 1000
    cfg.track_success()
    cfg.track_duration(int(latency_ms))
    return RoomPlan(room=inp.room, plan_text=text,
                    latency_ms=latency_ms, model_used=model)


@activity.defn
def build_shopping_list(inp: ShoppingListInput) -> str:
    """After human approval, synthesize a consolidated shopping list."""
    settings = get_settings()
    plans = "\n\n".join(f"## {p['room']}\n{p['plan_text']}" for p in inp.approved_plans)
    user = (f"Budget: {inp.budget}\n\nApproved room plans:\n{plans}\n\n"
            "Produce a single consolidated shopping list across all rooms.")
    text, _ = _invoke_with_fallback(
        ROOM_PLANNER_PROMPT, user, settings.default_model, settings.max_tokens, 1.0)
    return text