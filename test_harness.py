from app.harness import bindings_from_mcp_tools, inject_context_key, run_agent
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


if __name__ == "__main__":
    test_empty_message_rejected()
    print("PASS test_empty_message_rejected")
    test_long_message_rejected()
    print("PASS test_long_message_rejected")
    test_inject_context_key()
    print("PASS test_inject_context_key")
    test_bindings_come_from_tools_list()
    print("PASS test_bindings_come_from_tools_list")
