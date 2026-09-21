"""Host-side flinch gate. Runs before MCP tools/call. The MCP server stays model-free."""

from __future__ import annotations

from typing import Any

from app.flinch_check import decide
from app.flinch_state import state_for_tool
from app.flinch_telemetry import record_flinch_decision
from app.logging import get_logger

log = get_logger(__name__)


class FlinchStopped:
    """Looks enough like an MCP tool result for parse_mcp_payload."""

    def __init__(self, payload: dict):
        self.structured_content = payload
        self.content = []


async def call_tool(
    client: Any,
    name: str,
    args: dict,
    *,
    context_key: str,
    stated_intent: str,
) -> Any:
    state = state_for_tool(
        name, stated_intent=stated_intent, context_key=context_key
    )
    verdict = decide(state)
    try:
        record_flinch_decision(state=state, verdict=verdict, context_key=context_key)
    except Exception:
        log.exception("harness.flinch_telemetry_failed", tool=name)
    if verdict.get("enforce") and verdict.get("decision") != "allow":
        log.warning(
            "harness.flinch_stopped",
            tool=name,
            decision=verdict.get("decision"),
            reason=verdict.get("reason"),
        )
        return FlinchStopped(
            {
                "ok": False,
                "flinch": "stopped",
                "decision": verdict.get("decision"),
                "reason": verdict.get("reason"),
                "environment": (state.get("environment") or {}).get("name"),
            }
        )
    return await client.call_tool(name, args)
