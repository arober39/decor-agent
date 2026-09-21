from app.flinch_check import classify_command, decide
from app.flinch_gate import FlinchStopped, call_tool
from app.flinch_state import state_for_tool
import anyio


def test_classify_mcp_tool_names() -> None:
    assert classify_command("search_catalog") == "read-only"
    assert classify_command("update_project") == "write"
    assert classify_command("DELETE http://localhost:6334/collections/decor_catalog") == (
        "destructive"
    )


def test_project_writes_are_local_and_allowed() -> None:
    state = state_for_tool(
        "update_project",
        stated_intent="swap the sofa",
        context_key="test",
    )
    assert state["sensitivity"] == "local"
    verdict = decide(state, policy={"mode": "live", "destructive": {"local": "confirm", "shared": "block"}})
    assert verdict["kind"] == "write"
    assert verdict["decision"] == "allow"
    assert verdict["enforce"] is True


def test_search_catalog_is_shared_read_only_allow() -> None:
    state = state_for_tool(
        "search_catalog",
        stated_intent="warm minimalist sofa",
        context_key="test",
    )
    assert state["sensitivity"] == "shared"
    verdict = decide(state, policy={"mode": "live", "destructive": {"local": "confirm", "shared": "block"}})
    assert verdict["kind"] == "read-only"
    assert verdict["decision"] == "allow"


class _FakeClient:
    def __init__(self) -> None:
        self.called = []

    async def call_tool(self, name, args):
        self.called.append((name, args))
        return {"ok": True}


def test_gate_stops_enforced_destructive() -> None:
    client = _FakeClient()

    async def inner():
        return await call_tool(
            client,
            "ingest_catalog.recreate",
            {},
            context_key="test",
            stated_intent="fix schema on local-test",
        )

    stopped = anyio.run(inner)
    assert isinstance(stopped, FlinchStopped)
    assert stopped.structured_content["decision"] in {"block", "confirm"}
    assert client.called == []
