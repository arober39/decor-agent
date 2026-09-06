"""Call search_catalog through MCP, not by importing the function."""

from __future__ import annotations

import json

import anyio
from mcp import Client

from mcp_servers.decor_design import server


async def _run() -> None:
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


def test_search_catalog_over_mcp() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    test_search_catalog_over_mcp()
    print("PASS test_mcp_catalog")
