import time

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import ToolException, tool

from app.config import get_settings
from app.logging import get_logger
from app.prompts import TREND_SPOTTER_PROMPT

log = get_logger(__name__)


@tool("trend_spotter")
def trend_spotter(question: str) -> str:
    """Get information about current interior design trends. Use this when the user asks what's trendy, what's outdated, what's emerging, whether a style is still popular, or about design movement trajectories."""
    settings = get_settings()

    log.info("tool.invoke", tool="trend_spotter", question_len=len(question))

    start = time.perf_counter()
    try:
        llm = ChatAnthropic(
            model=settings.default_model,
            max_tokens=settings.max_tokens,
            api_key=settings.anthropic_api_key,
        )
        response = llm.invoke(
            [
                SystemMessage(content=TREND_SPOTTER_PROMPT),
                HumanMessage(content=question),
            ]
        )
        latency_ms = (time.perf_counter() - start) * 1000
        log.info("tool.success", tool="trend_spotter", latency_ms=round(latency_ms, 2))
        return response.content
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        log.error(
            "tool.error",
            tool="trend_spotter",
            error=str(exc),
            latency_ms=round(latency_ms, 2),
        )
        raise ToolException(f"trend_spotter failed: {exc}") from exc
