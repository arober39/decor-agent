from langchain_core.messages import AIMessage, ToolMessage

from app.config import get_settings
from app.logging import get_logger
from app.state import AgentState

log = get_logger(__name__)

FALLBACK_MESSAGE = (
    "I'm having trouble processing that right now. Could you try rephrasing "
    "your question, or I can connect you with a design consultant."
)


def _detect_error(state: AgentState) -> tuple[bool, str | None, str | None]:
    """Return (has_error, error_text, failing_tool).

    The most recent ToolMessage is the ground truth — its status reflects
    the latest attempt. current_error is only consulted as a fallback signal
    when no ToolMessage is present.
    """
    messages = state.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            if getattr(msg, "status", None) == "error":
                content = msg.content if isinstance(msg.content, str) else str(msg.content)
                return True, content, getattr(msg, "name", None)
            return False, None, None

    current_error = state.get("current_error")
    if current_error:
        return True, current_error, None
    return False, None, None


def error_handler(state: AgentState) -> dict:
    settings = get_settings()
    has_error, error_text, failing_tool = _detect_error(state)

    if not has_error:
        log.info("error_handler.no_error")
        return {}

    new_count = state.get("error_count", 0) + 1

    if new_count <= settings.max_retries:
        log.warning(
            "error_handler.retry",
            attempt=new_count,
            max_retries=settings.max_retries,
            failing_tool=failing_tool,
            error=error_text,
        )
        return {
            "error_count": new_count,
            "current_error": error_text,
            "metadata": {
                "error_handler": {
                    "action": "retry",
                    "attempt": new_count,
                    "failing_tool": failing_tool,
                }
            },
        }

    log.error(
        "error_handler.exhausted",
        attempts=new_count,
        max_retries=settings.max_retries,
        failing_tool=failing_tool,
        error=error_text,
    )
    return {
        "messages": [AIMessage(content=FALLBACK_MESSAGE)],
        "error_count": new_count,
        "current_error": error_text,
        "metadata": {
            "error_handler": {
                "action": "fallback",
                "attempts": new_count,
                "failing_tool": failing_tool,
            }
        },
    }
