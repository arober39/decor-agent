import time

from langchain_core.messages import SystemMessage

from app.config import get_settings
from app.flags import (
    AIConfigDefault,
    build_context,
    get_completion_config,
    set_current_context_key,
)
from app.llm import get_llm
from app.logging import get_logger
from app.prompts import AGENT_SYSTEM_PROMPT
from app.state import AgentState
from app.tools import get_tools

log = get_logger(__name__)


def agent_node(state: AgentState) -> dict:
    settings = get_settings()
    context_key = state.get("context_key") or "anonymous"
    set_current_context_key(context_key)
    tools = get_tools(context_key)
    context = build_context(context_key)
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=AGENT_SYSTEM_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-agent-main", context, default)

    llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature)
    llm_with_tools = llm.bind_tools(tools)

    messages = [SystemMessage(content=cfg.system_prompt), *state["messages"]]

    start = time.perf_counter()
    try:
        response = llm_with_tools.invoke(messages)
    except Exception:
        cfg.track_error()
        raise
    latency_ms = int((time.perf_counter() - start) * 1000)

    tool_calls = getattr(response, "tool_calls", []) or []
    usage = getattr(response, "usage_metadata", None) or {}
    cfg.track_success()
    cfg.track_duration(latency_ms)
    if usage:
        cfg.track_tokens(usage.get("input_tokens", 0), usage.get("output_tokens", 0))

    log.info(
        "agent.invoke",
        model=cfg.model,
        variation=cfg.variation,
        source=cfg.source,
        latency_ms=latency_ms,
        has_tool_calls=bool(tool_calls),
        tools_selected=[tc["name"] for tc in tool_calls],
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        total_tokens=usage.get("total_tokens"),
    )

    return {
        "messages": [response],
        "metadata": {
            "agent": {
                "model": cfg.model,
                "variation": cfg.variation,
                "source": cfg.source,
                "latency_ms": latency_ms,
                "tools_selected": [tc["name"] for tc in tool_calls],
                "usage": usage,
            }
        },
    }
