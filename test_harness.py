from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.harness import (
    _final_text,
    bindings_from_mcp_tools,
    commentary_from_project,
    inject_context_key,
    run_agent,
    run_agent_async,
)
from app import store
from mcp import Client
from mcp_servers.decor_design import server
import anyio


def test_empty_message_rejected() -> None:
    out = run_agent("", "guard-empty")
    assert out["metadata"]["routed_to"] == "rejected"
    assert out["response"]


def test_long_message_rejected() -> None:
    out = run_agent("a" * 3000, "guard-long")
    assert out["metadata"]["routed_to"] == "rejected"


def test_final_text_keeps_preamble_on_tool_turn() -> None:
    msg = AIMessage(
        content=[
            {"type": "text", "text": "Sourcing the living room now."},
            {"type": "tool_use", "name": "search_catalog"},
        ],
        tool_calls=[{"name": "search_catalog", "args": {"query": "sofa"}, "id": "1"}],
    )
    assert (
        _final_text([HumanMessage(content="plan a room"), msg])
        == "Sourcing the living room now."
    )


def test_final_text_empty_when_only_tools() -> None:
    msg = AIMessage(
        content="",
        tool_calls=[{"name": "search_catalog", "args": {}, "id": "1"}],
    )
    assert _final_text([msg, ToolMessage(content="{}", tool_call_id="1")]) == ""


def test_commentary_from_project_names_catalog_rows() -> None:
    text = commentary_from_project(
        {"spec_list": [{"name": "Sven 72-inch sofa", "sku": "ART-SOFA-721"}]}
    )
    assert "ART-SOFA-721" in text
    assert "Sven" in text


def test_inject_context_key() -> None:
    args = inject_context_key("update_project", {"action": "set_budget"}, "job-9")
    assert args["context_key"] == "job-9"
    search = inject_context_key("search_catalog", {"query": "sofa"}, "job-9")
    assert "context_key" not in search


async def _list_bindings() -> None:
    store.reset()
    async with Client(server) as client:
        listed = await client.list_tools()
        bindings = bindings_from_mcp_tools(listed.tools)
        names = {item["name"] for item in bindings}
        assert names == {"search_catalog", "update_project", "request_approval"}
        for item in bindings:
            assert "input_schema" in item


def test_bindings_come_from_tools_list() -> None:
    anyio.run(_list_bindings)


def test_async_entry_works_inside_running_loop() -> None:
    """FastAPI already has an event loop. anyio.run() would raise there."""

    async def inner() -> dict:
        return await run_agent_async("   ", "guard-nested-loop")

    out = anyio.run(inner)
    assert out["metadata"]["routed_to"] == "rejected"
    assert out["response"]


def test_chat_route_does_not_start_a_second_loop() -> None:
    from fastapi.testclient import TestClient

    from server import app

    client = TestClient(app)
    response = client.post(
        "/api/chat",
        json={"message": "   ", "context_key": "guard-http-loop"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["routed_to"] == "rejected"


if __name__ == "__main__":
    test_empty_message_rejected()
    print("PASS test_empty_message_rejected")
    test_long_message_rejected()
    print("PASS test_long_message_rejected")
    test_final_text_keeps_preamble_on_tool_turn()
    print("PASS test_final_text_keeps_preamble_on_tool_turn")
    test_final_text_empty_when_only_tools()
    print("PASS test_final_text_empty_when_only_tools")
    test_commentary_from_project_names_catalog_rows()
    print("PASS test_commentary_from_project_names_catalog_rows")
    test_inject_context_key()
    print("PASS test_inject_context_key")
    test_bindings_come_from_tools_list()
    print("PASS test_bindings_come_from_tools_list")
    test_async_entry_works_inside_running_loop()
    print("PASS test_async_entry_works_inside_running_loop")
    test_chat_route_does_not_start_a_second_loop()
    print("PASS test_chat_route_does_not_start_a_second_loop")
