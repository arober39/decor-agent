import time

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import ToolException, tool

from app.config import get_settings
from app.logging import get_logger
from app.prompts import STYLE_ADVISOR_PROMPT

log = get_logger(__name__)


@tool("style_advisor")
def style_advisor(question: str, style_preferences: str = "not specified") -> str:
    """Get interior design style advice. Use this for questions about design styles, color palettes, material choices, furniture pairing, aesthetic direction, or 'should I go with X or Y' style comparisons."""
    settings = get_settings()

    user_content = question
    if style_preferences and style_preferences != "not specified":
        user_content = f"Style preferences: {style_preferences}\n\nQuestion: {question}"

    log.info(
        "tool.invoke",
        tool="style_advisor",
        question_len=len(question),
        has_preferences=style_preferences != "not specified",
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
                SystemMessage(content=STYLE_ADVISOR_PROMPT),
                HumanMessage(content=user_content),
            ]
        )
        latency_ms = (time.perf_counter() - start) * 1000
        log.info("tool.success", tool="style_advisor", latency_ms=round(latency_ms, 2))
        return response.content
    except Exception as exc:
        latency_ms = (time.perf_counter() - start) * 1000
        log.error(
            "tool.error",
            tool="style_advisor",
            error=str(exc),
            latency_ms=round(latency_ms, 2),
        )
        raise ToolException(f"style_advisor failed: {exc}") from exc
