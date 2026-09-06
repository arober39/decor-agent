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


def test_update_project_over_mcp() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    test_update_project_over_mcp()
    print("PASS test_mcp_project")
