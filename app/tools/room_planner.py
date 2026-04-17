import time

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import ToolException, tool

from app.config import get_settings
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
        question_len=len(question),
        has_dimensions=room_dimensions != "not specified",
        has_budget=budget != "not specified",
    )

    start = time.perf_counter()
    try:
        llm = ChatAnthropic(
            model=settings.default_model,
            max_tokens=settings.max_tokens,
            api_key=settings.anthropic_api_key,
        )
        response = llm.invoke(
            [
                SystemMessage(content=ROOM_PLANNER_PROMPT),
                HumanMessage(content=user_content),
            ]
        )
        latency_ms = (time.perf_counter() - start) * 1000
        log.info("tool.success", tool="room_planner", latency_ms=round(latency_ms, 2))
        return response.content
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        log.error(
            "tool.error",
            tool="room_planner",
            error=str(exc),
            latency_ms=round(latency_ms, 2),
        )
        raise ToolException(f"room_planner failed: {exc}") from exc
