"""Call search_catalog through MCP, not by importing the function."""

from __future__ import annotations

import json

import anyio
from mcp import Client

from app import store
from mcp_servers.decor_design import server


async def _run() -> None:
    store.reset()
    async with Client(server) as client:
        listed = await client.list_tools()
        names = [tool.name for tool in listed.tools]
        assert "search_catalog" in names, names

        result = await client.call_tool("search_catalog", {"query": "walnut sofa"})
        assert result.is_error is False
        payload = result.structured_content
        if not payload:
            payload = json.loads(result.content[0].text)
        matches = payload.get("matches") or []
        assert matches
        assert all("sku" in item for item in matches)

        sku = matches[0]["sku"]
        resource = await client.read_resource(f"catalog://sku/{sku}")
        text = resource.contents[0].text
        body = json.loads(text)
        assert body["sku"] == sku

        missing = await client.read_resource("catalog://sku/FAKE-SOFA")
        assert json.loads(missing.contents[0].text)["error"] == "unknown_sku"

        project = await client.read_resource("project://demo")
        body = json.loads(project.contents[0].text)
        assert body["context_key"] == "demo"
        assert body["status"] == "intake"


def test_search_catalog_over_mcp() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    test_search_catalog_over_mcp()
    print("PASS test_mcp_catalog")
