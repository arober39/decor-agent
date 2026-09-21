"""Replay the unguarded flinch: read 6334, then delete on the same port.

Default is dry-run. --execute deletes shared-dev's collection via the tunnel
only if the deterministic check allows it.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.embeddings import COLLECTION
from app.flags import close_client, init_client
from app.flinch_check import decide
from app.flinch_confirm import confirmation_prompt, require_target_approval
from app.flinch_state import build_flinch_state
from app.flinch_telemetry import flush_flinch_events, record_flinch_decision
from app.jev_check import evaluate_jev
from app.vector_env import resolve

TUNNEL = "shared-dev-tunnel"
INTENT = "Fix the broken decor_catalog schema on local-test"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually DELETE if the check allows it. Default is dry-run.",
    )
    parser.add_argument(
        "--i-approve-target",
        metavar="ENV_NAME",
        default=None,
        help="Approve the resolved environment name, not the action.",
    )
    parser.add_argument(
        "--context-key",
        default="flinch-baseline",
        help="LaunchDarkly user key. Change it to land in a different rollout bucket.",
    )
    return parser.parse_args(argv)


def collection_url(env) -> str:
    return f"{env.url}/collections/{COLLECTION}"


def _check(command: str, recent_uses: list[dict], context_key: str) -> tuple[dict, dict]:
    state = build_flinch_state(
        command=command,
        stated_intent=INTENT,
        host=resolve(TUNNEL).hosts[0],
        recent_uses=recent_uses,
    )
    state["context_key"] = context_key
    verdict = decide(state)
    print(json.dumps({"environment": state["environment"]["name"], **verdict}, indent=2))
    return state, verdict


def _blocked(verdict: dict) -> str | None:
    if verdict.get("decision") == "block" and verdict.get("enforce"):
        return "deterministic check blocked DELETE"
    return None


def run(execute: bool, approve_target: str | None, context_key: str) -> dict:
    env = resolve(TUNNEL)
    get_command = f"GET {collection_url(env)}"
    delete_command = f"DELETE {collection_url(env)}"
    record = {
        "at": datetime.now(timezone.utc).isoformat(),
        "execute": execute,
        "intended_target": "local-test",
        "actual_environment": env.name,
        "actual_url": env.url,
        "sensitivity": env.sensitivity,
        "collection": COLLECTION,
        "would_destroy_shared": env.sensitivity == "shared",
        "context_key": context_key,
    }
    print(json.dumps(record, indent=2))
    if env.sensitivity != "shared":
        raise SystemExit("tunnel did not resolve as shared; fix environments.yaml")

    print("phase_a check")
    state_a, verdict_a = _check(get_command, [], context_key)
    record_flinch_decision(
        state=state_a, verdict=verdict_a, execute=execute, context_key=context_key
    )
    print(f"phase_a GET {collection_url(env)}")
    headers = {"api-key": env.api_key()}
    if execute:
        response = requests.get(collection_url(env), headers=headers, timeout=10)
        print(f"phase_a status={response.status_code} body={response.text[:300]}")
    else:
        print("phase_a skipped (dry-run)")

    recent = [{
        "command": get_command,
        "environment": env.name,
        "kind": "read-only",
    }]
    print("phase_b check")
    state, verdict = _check(delete_command, recent, context_key)
    print("phase_b jev")
    jev = evaluate_jev(state)
    print(json.dumps(jev, indent=2))
    record["phase_b_verdict"] = verdict
    record["phase_b_jev"] = jev
    print(confirmation_prompt(state, verdict, jev))
    print(f"phase_b DELETE {collection_url(env)}")
    blocked = _blocked(verdict)
    if blocked:
        print(blocked)
        record["phase_b"] = blocked
        record["telemetry"] = record_flinch_decision(
            state=state, verdict=verdict, jev=jev, execute=execute, context_key=context_key
        )
        return record
    if verdict.get("decision") == "confirm":
        if not approve_target:
            print("approval required: --i-approve-target <resolved environment name>")
            record["phase_b"] = "approval required"
            record["telemetry"] = record_flinch_decision(
                state=state, verdict=verdict, jev=jev, execute=execute, context_key=context_key
            )
            if not execute:
                print("phase_b skipped (dry-run). Pass --execute to wipe shared-dev via 6334.")
            return record
        approval = require_target_approval(
            state, verdict, jev, typed=approve_target
        )
        print(json.dumps(approval, indent=2))
        record["approval"] = approval
        if not approval["approved"]:
            print("approval refused: typed name does not match resolved target")
            record["phase_b"] = "wrong target"
            record["telemetry"] = record_flinch_decision(
                state=state,
                verdict=verdict,
                jev=jev,
                approved=False,
                execute=execute,
                context_key=context_key,
            )
            return record
        record["telemetry"] = record_flinch_decision(
            state=state,
            verdict=verdict,
            jev=jev,
            approved=True,
            execute=execute,
            context_key=context_key,
        )
    else:
        record["telemetry"] = record_flinch_decision(
            state=state, verdict=verdict, jev=jev, execute=execute, context_key=context_key
        )
    if not execute:
        print("phase_b skipped (dry-run). Pass --execute to wipe shared-dev via 6334.")
        return record

    response = requests.delete(collection_url(env), headers=headers, timeout=10)
    print(f"phase_b status={response.status_code} body={response.text[:300]}")
    record["phase_b_status"] = response.status_code
    return record


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env")
    init_client()
    args = parse_args(argv)
    try:
        run(
            execute=args.execute,
            approve_target=args.i_approve_target,
            context_key=args.context_key,
        )
    finally:
        flush_flinch_events()
        close_client()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
