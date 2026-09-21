"""Build named JSON state for a flinch check. No Qdrant. No Jev."""

from __future__ import annotations

from app.embeddings import COLLECTION
from app.flinch_check import load_tools
from app.vector_env import resolve, resolve_by_host


def build_flinch_state(
    *,
    command: str,
    stated_intent: str,
    host: str,
    collection: str = COLLECTION,
    recent_uses: list[dict] | None = None,
) -> dict:
    env = resolve_by_host(host)
    return {
        "command": command,
        "stated_intent": stated_intent,
        "resolved_target": {
            "host": env.hosts[0],
            "url": env.url,
            "collection": collection,
        },
        "environment": {
            "name": env.name,
            "sensitivity": env.sensitivity,
            "hosts": list(env.hosts),
            "notes": env.notes,
        },
        "sensitivity": env.sensitivity,
        "recent_uses": list(recent_uses or []),
    }


def state_for_tool(
    name: str,
    *,
    stated_intent: str,
    context_key: str,
    recent_uses: list[dict] | None = None,
) -> dict:
    """Build flinch state for an MCP tool name. Empty targets are the in-memory store."""
    row = next((tool for tool in load_tools() if tool.get("name") == name), None) or {}
    targets = list(row.get("targets") or [])
    if targets:
        env = resolve(str(targets[0]))
        state = build_flinch_state(
            command=name,
            stated_intent=stated_intent,
            host=env.hosts[0],
            recent_uses=recent_uses,
        )
    else:
        state = {
            "command": name,
            "stated_intent": stated_intent,
            "resolved_target": {
                "host": "project-store",
                "url": "",
                "collection": "",
            },
            "environment": {
                "name": "decora-project",
                "sensitivity": "local",
                "hosts": [],
                "notes": "In-memory project store, not Qdrant.",
            },
            "sensitivity": "local",
            "recent_uses": list(recent_uses or []),
        }
    state["context_key"] = context_key
    return state
