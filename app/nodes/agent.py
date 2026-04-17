import time

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage

from app.config import get_settings
from app.logging import get_logger
from app.prompts import AGENT_SYSTEM_PROMPT
from app.state import AgentState
from app.tools import get_tools

log = get_logger(__name__)


def agent_node(state: AgentState) -> dict:
    settings = get_settings()
    tools = get_tools(state.get("context_key"))

    llm = ChatAnthropic(
        model=settings.default_model,
        max_tokens=settings.max_tokens,
        api_key=settings.anthropic_api_key,
    )
    llm_with_tools = llm.bind_tools(tools)

    messages = [SystemMessage(content=AGENT_SYSTEM_PROMPT), *state["messages"]]

    start = time.perf_counter()
    response = llm_with_tools.invoke(messages)
    latency_ms = (time.perf_counter() - start) * 1000

    tool_calls = getattr(response, "tool_calls", []) or []
    usage = getattr(response, "usage_metadata", None) or {}

    log.info(
        "agent.invoke",
        model=settings.default_model,
        latency_ms=round(latency_ms, 2),
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
                "model": settings.default_model,
                "latency_ms": round(latency_ms, 2),
                "tools_selected": [tc["name"] for tc in tool_calls],
                "usage": usage,
            }
        },
    }
