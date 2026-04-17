from datetime import datetime, timezone

from langchain_core.messages import AIMessage

from app.logging import get_logger
from app.state import AgentState

log = get_logger(__name__)


def _final_ai_text(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not (getattr(msg, "tool_calls", []) or []):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
    return ""


def _tool_calls_made(messages: list) -> list[str]:
    calls: list[str] = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in getattr(msg, "tool_calls", []) or []:
                calls.append(tc["name"])
    return calls


def format_response(state: AgentState) -> dict:
    messages = state.get("messages", [])
    tool_calls_made = _tool_calls_made(messages)
    routed_to = tool_calls_made[0] if tool_calls_made else "direct"
    final_text = _final_ai_text(messages)

    metadata = {
        "routed_to": routed_to,
        "tool_calls_made": tool_calls_made,
        "total_messages": len(messages),
        "error_count": state.get("error_count", 0),
        "context_key": state.get("context_key", "anonymous"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log.info(
        "response_formatter.done",
        routed_to=routed_to,
        tool_calls_made=tool_calls_made,
        total_messages=metadata["total_messages"],
        error_count=metadata["error_count"],
        context_key=metadata["context_key"],
        response_len=len(final_text),
    )

    return {"metadata": metadata}
