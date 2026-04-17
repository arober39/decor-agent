import re

from langchain_core.messages import AIMessage, HumanMessage

from app.config import get_settings
from app.logging import get_logger
from app.state import AgentState

log = get_logger(__name__)

PII_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(r"(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def _last_user_text(state: AgentState) -> str | None:
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, HumanMessage):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
    return None


def _reject(reason: str, user_message: str) -> dict:
    log.warning("input_guard.reject", reason=reason)
    return {
        "input_valid": False,
        "messages": [AIMessage(content=user_message)],
        "metadata": {"input_guard": {"rejected": True, "reason": reason}},
    }


def input_guard(state: AgentState) -> dict:
    settings = get_settings()
    text = _last_user_text(state)

    if text is None:
        return _reject(
            "no_user_message",
            "I didn't receive a message. Could you share what you'd like help with?",
        )

    stripped = text.strip()
    if not stripped:
        return _reject(
            "empty_message",
            "Your message looks empty. Tell me a bit about what you're working on and I'll help.",
        )

    if len(text) > settings.max_input_length:
        return _reject(
            "too_long",
            f"Your message is a bit long for me to process well ({len(text)} chars, max {settings.max_input_length}). Could you trim it down to the core question?",
        )

    pii_found = [name for name, pattern in PII_PATTERNS.items() if pattern.search(text)]
    if pii_found:
        log.warning("input_guard.pii_detected", types=pii_found)

    log.info(
        "input_guard.pass",
        length=len(text),
        pii_types=pii_found,
    )

    metadata: dict = {"input_guard": {"rejected": False, "length": len(text)}}
    if pii_found:
        metadata["input_guard"]["pii_types"] = pii_found

    return {"input_valid": True, "metadata": metadata}
