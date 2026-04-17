from typing import Annotated

from langgraph.graph import MessagesState


def merge_metadata(left: dict | None, right: dict | None) -> dict:
    """Shallow-merge reducer so every node's metadata contribution survives."""
    return {**(left or {}), **(right or {})}


class AgentState(MessagesState):
    context_key: str
    input_valid: bool
    error_count: int
    current_error: str | None
    metadata: Annotated[dict, merge_metadata]


def default_state(message: str, context_key: str = "anonymous") -> dict:
    """Return a fully-initialized input dict for graph.invoke()."""
    from langchain_core.messages import HumanMessage
    return {
        "messages": [HumanMessage(content=message)],
        "context_key": context_key,
        "input_valid": True,
        "error_count": 0,
        "current_error": None,
        "metadata": {},
    }
