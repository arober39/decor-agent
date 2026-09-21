"""Host-only target approval. The model does not call this."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from getpass import getuser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPROVAL_LOG = ROOT / "logs" / "flinch-approvals.jsonl"


def target_token(state: dict) -> str:
    env = state.get("environment") or {}
    return str(env.get("name") or "").strip()


def confirmation_prompt(state: dict, verdict: dict, jev: dict) -> str:
    env = state.get("environment") or {}
    target = state.get("resolved_target") or {}
    nouls = jev.get("nouls") or {}
    name = target_token(state)
    return "\n".join(
        [
            "flinch confirmation (approve the TARGET, not the action)",
            f"command: {state.get('command')}",
            f"stated_intent: {state.get('stated_intent')}",
            f"resolved_name: {name}",
            f"hosts: {env.get('hosts')}",
            f"url: {target.get('url')}",
            f"collection: {target.get('collection')}",
            f"sensitivity: {env.get('sensitivity') or state.get('sensitivity')}",
            f"deterministic: {verdict.get('decision')} ({verdict.get('reason')})",
            f"jev_model: {jev.get('model')} source={jev.get('source')}",
            f"jev_nouls: {json.dumps(nouls, sort_keys=True)}",
            f"jev_action: {jev.get('action')} suggested={jev.get('suggested')} confidence={jev.get('confidence')}",
            f"type this environment name to approve: {name}",
        ]
    )


def record_approval(
    *,
    who: str,
    state: dict,
    verdict: dict,
    jev: dict,
    approved: bool,
    typed: str,
    path: Path | None = None,
) -> dict:
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "who": who,
        "approved": approved,
        "typed": typed,
        "target": target_token(state),
        "command": state.get("command"),
        "decision": verdict.get("decision"),
        "jev_model": jev.get("model"),
        "jev_suggested": jev.get("suggested"),
    }
    dest = path or APPROVAL_LOG
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return row


def require_target_approval(
    state: dict,
    verdict: dict,
    jev: dict,
    *,
    typed: str,
    who: str | None = None,
    path: Path | None = None,
) -> dict:
    token = target_token(state)
    approved = bool(token) and typed.strip() == token
    return record_approval(
        who=who or getuser(),
        state=state,
        verdict=verdict,
        jev=jev,
        approved=approved,
        typed=typed,
        path=path,
    )
