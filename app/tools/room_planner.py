import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import ToolException, tool

from app.config import get_settings
from app.flags import (
    AIConfigDefault,
    build_context,
    current_context_key,
    get_completion_config,
)
from app.llm import get_llm
from app.logging import get_logger
from app.prompts import ROOM_PLANNER_PROMPT

log = get_logger(__name__)


@tool("room_planner")
def room_planner(
    question: str,
    room_dimensions: str = "not specified",
    budget: str = "not specified",
) -> str:
    """Plan a room layout and optimize how a space feels. Use this when the user mentions room dimensions, square footage, furniture placement, traffic flow, fitting furniture in a space, small-space problems (e.g. making a small room feel bigger, working around awkward layouts), furniture scale relative to room size, or has a specific budget for furnishing. Prefer this tool whenever the question centers on a physical space or how to use its square footage — even if color or material choices are part of the answer."""
    settings = get_settings()
    context = build_context(current_context_key())
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=ROOM_PLANNER_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-room-planner", context, default)

    parts = []
    if room_dimensions and room_dimensions != "not specified":
        parts.append(f"Room dimensions: {room_dimensions}")
    if budget and budget != "not specified":
        parts.append(f"Budget: {budget}")
    parts.append(f"Question: {question}")
    user_content = "\n\n".join(parts)

    log.info(
        "tool.invoke",
        tool="room_planner",
        model=cfg.model,
        variation=cfg.variation,
        source=cfg.source,
    )

    llm = get_llm(cfg.model, cfg.max_tokens, cfg.temperature)
    start = time.perf_counter()
    try:
        response = llm.invoke(
            [
                SystemMessage(content=cfg.system_prompt),
                HumanMessage(content=user_content),
            ]
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = getattr(response, "usage_metadata", None) or {}
        cfg.track_success()
        cfg.track_duration(latency_ms)
        if usage:
            cfg.track_tokens(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        log.info("tool.success", tool="room_planner", latency_ms=latency_ms)
        return response.content
    except Exception as exc:
        cfg.track_error()
        log.error("tool.error", tool="room_planner", error=str(exc))
        raise ToolException(f"room_planner failed: {exc}") from exc
