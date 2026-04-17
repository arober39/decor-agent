from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from app.config import get_settings
from app.logging import get_logger
from app.nodes.agent import agent_node
from app.nodes.error_handler import error_handler
from app.nodes.input_guard import input_guard
from app.nodes.response_formatter import format_response
from app.state import AgentState, default_state
from app.tools import get_tools

log = get_logger(__name__)


def _route_after_input_guard(state: AgentState) -> str:
    return "agent" if state.get("input_valid", True) else "response_formatter"


def _should_continue(state: AgentState) -> str:
    messages = state.get("messages", [])
    if not messages:
        return "response_formatter"
    last = messages[-1]
    tool_calls = getattr(last, "tool_calls", []) or []
    return "execute_tools" if tool_calls else "response_formatter"


def _route_after_error_handler(state: AgentState) -> str:
    if state.get("error_count", 0) > get_settings().max_retries:
        return "response_formatter"
    return "agent"


def build_graph():
    builder = StateGraph(AgentState)
    builder.add_node("input_guard", input_guard)
    builder.add_node("agent", agent_node)
    builder.add_node("execute_tools", ToolNode(get_tools()))
    builder.add_node("error_handler", error_handler)
    builder.add_node("response_formatter", format_response)

    builder.add_edge(START, "input_guard")
    builder.add_conditional_edges(
        "input_guard",
        _route_after_input_guard,
        {"agent": "agent", "response_formatter": "response_formatter"},
    )
    builder.add_conditional_edges(
        "agent",
        _should_continue,
        {"execute_tools": "execute_tools", "response_formatter": "response_formatter"},
    )
    builder.add_edge("execute_tools", "error_handler")
    builder.add_conditional_edges(
        "error_handler",
        _route_after_error_handler,
        {"agent": "agent", "response_formatter": "response_formatter"},
    )
    builder.add_edge("response_formatter", END)

    return builder.compile()


app = build_graph()


def _final_response_text(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not (getattr(msg, "tool_calls", []) or []):
            content = msg.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
            return str(content)
    return ""


def run_agent(message: str, context_key: str = "anonymous") -> dict:
    log.info("run_agent.start", context_key=context_key, message_len=len(message))
    result = app.invoke(default_state(message, context_key=context_key))
    response_text = _final_response_text(result.get("messages", []))
    metadata = result.get("metadata", {})
    log.info(
        "run_agent.done",
        context_key=context_key,
        routed_to=metadata.get("routed_to"),
        response_len=len(response_text),
    )
    return {"response": response_text, "metadata": metadata}
