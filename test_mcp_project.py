"""Mutate a project through MCP tools/call, then read it back as a resource."""

from __future__ import annotations

import json

import anyio
from mcp import Client

from app import store
from mcp_servers.decor_design import server


def _text(result) -> dict:
    if result.structured_content:
        return result.structured_content
    return json.loads(result.content[0].text)


async def _run() -> None:
    store.reset()
    async with Client(server) as client:
        listed = await client.list_tools()
        names = [tool.name for tool in listed.tools]
        assert "update_project" in names
        assert "apply_board" in names

        await client.call_tool(
            "update_project",
            {
                "context_key": "job-1",
                "action": "upsert_room",
                "room_name": "living room",
                "room_type": "living",
                "width_ft": 12,
                "length_ft": 14,
            },
        )
        await client.call_tool(
            "update_project",
            {"context_key": "job-1", "action": "set_budget", "budget_dollars": 2000},
        )
        added = await client.call_tool(
            "update_project",
            {
                "context_key": "job-1",
                "action": "add_spec",
                "sku": "ART-SOFA-721",
                "room_name": "living room",
            },
        )
        body = _text(added)
        assert body["spec_list"][0]["sku"] == "ART-SOFA-721"
        assert body["spec_list"][0]["status"] == "draft"

        fake = await client.call_tool(
            "update_project",
            {"context_key": "job-1", "action": "add_spec", "sku": "FAKE", "room_name": "living room"},
        )
        assert "error" in _text(fake)

        resource = await client.read_resource("project://job-1")
        assert json.loads(resource.contents[0].text)["budget"]["total_cents"] == 200000

        gated = await client.call_tool(
            "request_approval",
            {"context_key": "job-1", "kind": "spec", "summary": "Living room sofa under budget."},
        )
        gated_body = _text(gated)
        assert gated_body["pending_approval"] is True
        assert gated_body["spec_list"][0]["status"] == "draft"

        prompts = await client.list_prompts()
        assert any(prompt.name == "plan_room" for prompt in prompts.prompts)
        got = await client.get_prompt("plan_room", {"room": "12x14 living room", "budget_dollars": "2000"})
        text = got.messages[0].content.text
        assert "12x14 living room" in text
        assert "2000" in text

        store.reset()
        mapped = await client.call_tool(
            "apply_board",
            {"context_key": "board-mcp", "room_name": "living room", "budget_dollars": 2000},
        )
        mapped_body = _text(mapped)
        assert mapped_body["spec_list"][0]["sku"]
        assert any(item["lane"] == "close" for item in mapped_body["spec_list"])
        assert mapped_body["skipped"] == []
        assert mapped_body["pending_approval"] is True


def test_update_project_over_mcp() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    test_update_project_over_mcp()
    print("PASS test_mcp_project")
