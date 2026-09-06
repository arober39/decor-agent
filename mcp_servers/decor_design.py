"""decor-design MCP server.

This process is the environment. It does not call Claude.
A host (Decora, goose, Inspector) connects and calls tools over MCP.
"""

from __future__ import annotations

from mcp.server import MCPServer

from app.catalog import get_product, search_products
from app import store

server = MCPServer(
    name="decor-design",
    title="Decor Design",
    instructions=(
        "Interior design environment. Search the catalog for real SKUs. "
        "Do not invent products that search_catalog did not return."
    ),
)


@server.tool()
def search_catalog(
    query: str,
    category: str = "",
    room_type: str = "",
    max_price_dollars: float | None = None,
    limit: int = 5,
) -> dict:
    """Search the furniture catalog. Returns only real SKUs that exist in inventory.

    query: free text such as "walnut sofa" or "warm white paint for dark oak".
    category: optional filter (sofa, chair, table, bed, desk, rug, lighting, storage, paint, decor, hardware).
    room_type: optional filter (living, bedroom, kitchen, dining, bathroom, office).
    max_price_dollars: optional price ceiling.
    """
    max_cents = None
    if max_price_dollars is not None:
        max_cents = int(round(max_price_dollars * 100))
    matches = search_products(
        query=query,
        category=category,
        room_type=room_type,
        max_price_cents=max_cents,
        limit=limit,
    )
    return {"matches": [product.as_dict() for product in matches]}


@server.resource(
    "catalog://sku/{sku}",
    mime_type="application/json",
    description="Read one catalog product by SKU. Missing SKUs return an error body.",
)
def catalog_sku(sku: str) -> dict:
    product = get_product(sku)
    if product is None:
        return {"error": "unknown_sku", "sku": sku}
    return product.as_dict()


@server.resource(
    "project://{context_key}",
    mime_type="application/json",
    description="Read the durable design project for this client. Chat history is not the source of truth.",
)
def project_resource(context_key: str) -> dict:
    return store.snapshot(context_key)


if __name__ == "__main__":
    server.run(transport="stdio")
