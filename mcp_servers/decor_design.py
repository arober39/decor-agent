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


@server.tool()
def update_project(
    context_key: str,
    action: str,
    lifestyle: str = "",
    keep: str = "",
    avoid: str = "",
    style_preferences: str = "",
    budget_dollars: float | None = None,
    room_name: str = "",
    room_type: str = "living",
    width_ft: float | None = None,
    length_ft: float | None = None,
    existing_pieces: str = "",
    style_notes: str = "",
    sku: str = "",
) -> dict:
    """Create or update the durable design project for this client.

    action: set_brief | set_budget | upsert_room | add_spec | remove_spec
    keep, avoid, existing_pieces: comma-separated lists
    add_spec requires a sku returned by search_catalog
    """
    def _parts(value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    if action == "set_brief":
        store.set_brief(
            context_key,
            lifestyle=lifestyle,
            keep=_parts(keep) if keep else None,
            avoid=_parts(avoid) if avoid else None,
            style_preferences=style_preferences,
        )
    elif action == "set_budget":
        if budget_dollars is None:
            return {"error": "set_budget requires budget_dollars"}
        store.set_budget(context_key, budget_dollars)
    elif action == "upsert_room":
        if not room_name.strip():
            return {"error": "upsert_room requires room_name"}
        store.upsert_room(
            context_key,
            name=room_name,
            room_type=room_type,
            width_ft=width_ft,
            length_ft=length_ft,
            existing_pieces=_parts(existing_pieces) if existing_pieces else None,
            style_notes=style_notes or None,
        )
    elif action == "add_spec":
        try:
            store.add_spec(context_key, sku, room_name)
        except ValueError as exc:
            return {"error": str(exc)}
    elif action == "remove_spec":
        if not sku.strip():
            return {"error": "remove_spec requires sku"}
        store.remove_spec(context_key, sku)
    else:
        return {"error": f"unsupported action: {action}"}
    return store.snapshot(context_key)


@server.tool()
def request_approval(context_key: str, kind: str, summary: str) -> dict:
    """Pause the job and ask the human to approve concept, budget, or spec.

    After this call, stop sourcing. Do not mark items committed yourself.
    """
    if kind not in {"concept", "budget", "spec"}:
        return {"error": "kind must be concept, budget, or spec"}
    if not summary.strip():
        return {"error": "summary is required"}
    store.request_approval(context_key, kind, summary.strip())  # type: ignore[arg-type]
    return store.snapshot(context_key)


@server.prompt()
def plan_room(
    room: str,
    budget_dollars: str = "",
    keep: str = "",
    avoid: str = "",
) -> str:
    """Start a design job for one room. User-invoked — not a hidden system prompt."""
    budget_line = f"Budget: ${budget_dollars}." if budget_dollars else "Budget is not set yet."
    keep_line = f"Keep: {keep}." if keep else "Nothing required to keep."
    avoid_line = f"Avoid: {avoid}." if avoid else "No hard avoids."
    return (
        f"Plan the {room}. {budget_line} {keep_line} {avoid_line} "
        "Read project:// for this client, search the catalog for real SKUs, "
        "update the project, and request approval when the spec covers the room "
        "and the budget holds. Do not invent products."
    )


if __name__ == "__main__":
    server.run(transport="stdio")
