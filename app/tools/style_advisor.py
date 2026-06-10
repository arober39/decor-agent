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
from app.prompts import STYLE_ADVISOR_PROMPT

log = get_logger(__name__)


@tool("style_advisor")
def style_advisor(question: str, style_preferences: str = "not specified") -> str:
    """Get interior design style advice. Use this for questions about design styles, color palettes, material choices, furniture pairing, aesthetic direction, or 'should I go with X or Y' style comparisons."""
    settings = get_settings()
    context = build_context(current_context_key())
    default = AIConfigDefault(
        model=settings.default_model,
        system_prompt=STYLE_ADVISOR_PROMPT,
        max_tokens=settings.max_tokens,
    )
    cfg = get_completion_config("decor-style-advisor", context, default)

    user_content = question
    if style_preferences and style_preferences != "not specified":
        user_content = f"Style preferences: {style_preferences}\n\nQuestion: {question}"

    log.info(
        "tool.invoke",
        tool="style_advisor",
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
        log.info("tool.success", tool="style_advisor", latency_ms=latency_ms)
        return response.content
    except Exception as exc:
        cfg.track_error()
        log.error("tool.error", tool="style_advisor", error=str(exc))
        raise ToolException(f"style_advisor failed: {exc}") from exc
