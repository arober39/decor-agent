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
from app.prompts import TREND_SPOTTER_PROMPT

log = get_logger(__name__)


@tool("trend_spotter")
def trend_spotter(question: str) -> str:
    """Get information about current interior design trends. Use this when the user asks what's trendy, what's outdated, what's emerging, whether a style is still popular, or about design movement trajectories."""
    settings = get_settings()
    context = build_context(current_context_key())
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=TREND_SPOTTER_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-trend-spotter", context, default)

    log.info(
        "tool.invoke",
        tool="trend_spotter",
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
                HumanMessage(content=question),
            ]
        )
        latency_ms = int((time.perf_counter() - start) * 1000)
        usage = getattr(response, "usage_metadata", None) or {}
        cfg.track_success()
        cfg.track_duration(latency_ms)
        if usage:
            cfg.track_tokens(usage.get("input_tokens", 0), usage.get("output_tokens", 0))
        log.info("tool.success", tool="trend_spotter", latency_ms=latency_ms)
        return response.content
    except Exception as exc:
        cfg.track_error()
        log.error("tool.error", tool="trend_spotter", error=str(exc))
        raise ToolException(f"trend_spotter failed: {exc}") from exc
