"""Deterministic flinch check. No Jev. No Qdrant."""

from __future__ import annotations

import yaml

from app.flags import get_flinch_policy
from app.vector_env import REGISTRY_PATH

_KINDS = frozenset({"read-only", "write", "destructive"})


def load_tools(path=None) -> list[dict]:
    data = yaml.safe_load((path or REGISTRY_PATH).read_text()) or {}
    return list(data.get("tools") or [])


def _tool_matches(command: str, match: str) -> bool:
    cmd = command.strip()
    upper = cmd.upper()
    token = (match or "").strip()
    if not token:
        return False
    folded = token.upper().replace("{NAME}", "").replace("  ", " ")
    if "GET /COLLECTIONS" in folded:
        return upper.startswith("GET") and "/COLLECTIONS" in upper
    if "DELETE /COLLECTIONS" in folded:
        return "DELETE" in upper and "/COLLECTIONS" in upper
    return token.lower() in cmd.lower()


def classify_command(command: str, tools: list[dict] | None = None) -> str:
    cmd = (command or "").strip()
    for tool in tools if tools is not None else load_tools():
        kind = tool.get("kind")
        if kind not in _KINDS:
            continue
        name = str(tool.get("name") or "")
        if name and (cmd == name or cmd.startswith(name + " ")):
            return kind
        match = tool.get("match") or ""
        if match and _tool_matches(cmd, match):
            return kind
    upper = cmd.upper()
    if "DELETE" in upper and "/COLLECTIONS" in upper:
        return "destructive"
    if upper.startswith("GET"):
        return "read-only"
    return "write"


def decide(state: dict, policy: dict | None = None) -> dict:
    sensitivity = state.get("sensitivity") or "shared"
    policy = policy or get_flinch_policy(
        str(state.get("context_key") or "flinch-baseline"),
        qdrant_sensitivity=sensitivity,
    )
    kind = classify_command(str(state.get("command") or ""))
    mode = policy.get("mode") or "live"
    if kind == "read-only":
        decision = "allow"
        reason = "read-only command"
    elif kind == "write":
        decision = "confirm" if sensitivity == "shared" else "allow"
        reason = f"write on {sensitivity} target"
    else:
        destructive = policy.get("destructive") or {}
        decision = destructive.get(sensitivity) or "confirm"
        if sensitivity == "shared" and decision == "allow":
            decision = "confirm"
        reason = f"destructive action on {sensitivity} target"
    if mode == "off":
        return {
            "layer": "deterministic",
            "mode": mode,
            "kind": kind,
            "sensitivity": sensitivity,
            "decision": "allow",
            "enforce": False,
            "reason": "policy mode off",
        }
    enforce = mode == "live"
    return {
        "layer": "deterministic",
        "mode": mode,
        "kind": kind,
        "sensitivity": sensitivity,
        "decision": decision,
        "enforce": enforce,
        "reason": reason,
    }
