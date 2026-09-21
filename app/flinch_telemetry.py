"""Flinch decision log: JSONL backup, LD custom metrics, Observability logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.events import track
from app.flags import get_client
from app.logging import get_logger

log = get_logger(__name__)

ROOT = Path(__file__).resolve().parents[1]
DECISION_LOG = ROOT / "logs" / "flinch-decisions.jsonl"

EVENT_CHECK = "flinch_check"
EVENT_BLOCK = "flinch_block"
EVENT_ESCALATE = "flinch_escalate"
EVENT_OVERRIDE = "flinch_override"

_JEV_TO_DECISION = {
    "proceed": "allow",
    "confirm_with_human": "confirm",
    "block": "block",
}


def _map_jev(suggested: str | None) -> str | None:
    if not suggested:
        return None
    return _JEV_TO_DECISION.get(suggested)


def disagreement(verdict: dict, jev: dict | None) -> bool:
    if not jev:
        return False
    mapped = _map_jev(jev.get("suggested"))
    if mapped is None:
        return False
    return mapped != verdict.get("decision")


def resolve_outcome(
    *,
    verdict: dict,
    execute: bool,
    approved: bool | None,
) -> str:
    decision = verdict.get("decision")
    enforce = bool(verdict.get("enforce"))
    if decision == "allow":
        return "allowed"
    if decision == "block":
        return "blocked" if enforce else "would_block"
    if decision == "confirm":
        if approved is None:
            return "awaiting_approval"
        if not approved:
            return "approval_refused"
        if not execute:
            return "approved_dry_run"
        return "approved"
    return "would_confirm"


def record_flinch_decision(
    *,
    state: dict,
    verdict: dict,
    jev: dict | None = None,
    approved: bool | None = None,
    execute: bool = False,
    outcome: str | None = None,
    context_key: str = "flinch-baseline",
    path: Path | None = None,
) -> dict:
    jev = jev or {}
    env = state.get("environment") or {}
    row = {
        "at": datetime.now(timezone.utc).isoformat(),
        "command": state.get("command"),
        "environment": env.get("name"),
        "sensitivity": state.get("sensitivity") or env.get("sensitivity"),
        "kind": verdict.get("kind"),
        "policy_mode": verdict.get("mode"),
        "deterministic_decision": verdict.get("decision"),
        "enforce": bool(verdict.get("enforce")),
        "jev_source": jev.get("source"),
        "jev_model": jev.get("model"),
        "nouls": jev.get("nouls") or {},
        "jev_action": jev.get("action"),
        "jev_confidence": jev.get("confidence"),
        "jev_suggested": jev.get("suggested"),
        "outcome": outcome or resolve_outcome(
            verdict=verdict, execute=execute, approved=approved
        ),
        "disagreement": disagreement(verdict, jev),
    }
    if approved is not None:
        row["approval"] = approved

    dest = path or DECISION_LOG
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")

    data: dict[str, Any] = {
        "environment": row["environment"],
        "kind": row["kind"],
        "outcome": row["outcome"],
        "jev_model": row["jev_model"],
        "disagreement": row["disagreement"],
    }
    track(EVENT_CHECK, context_key, data, 1)
    outcome_name = row["outcome"]
    if outcome_name in {"blocked", "would_block"}:
        track(EVENT_BLOCK, context_key, data, 1)
    if (
        verdict.get("decision") == "confirm"
        or jev.get("suggested") == "confirm_with_human"
        or outcome_name == "awaiting_approval"
    ):
        track(EVENT_ESCALATE, context_key, data, 1)
    if approved is True:
        track(EVENT_OVERRIDE, context_key, data, 1)

    log.info("flinch.decision", **{k: v for k, v in row.items() if k != "nouls"})
    _observe_decision(row)
    return row


def _observe_attrs(row: dict) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            continue
        if key == "nouls" and isinstance(value, dict):
            for noul_name, noul_value in value.items():
                if isinstance(noul_value, (int, float)):
                    attrs[f"noul.{noul_name}"] = float(noul_value)
            continue
        if isinstance(value, (str, bool, int, float)):
            attrs[key] = value
        else:
            attrs[key] = json.dumps(value)
    return attrs


def _observe_decision(row: dict) -> None:
    try:
        from ldobserve import observe
    except ImportError:
        return
    try:
        attrs = _observe_attrs(row)
        extra = {
            f"flinch_{key.replace('.', '_')}": value
            for key, value in attrs.items()
        }
        logging.getLogger("ldobserve.observe").setLevel(logging.DEBUG)
        with observe.start_span("flinch.check", attributes=attrs) as span:
            span.add_event("flinch.decision", attributes=attrs)
            observe.record_log("flinch.decision", logging.INFO, extra)
    except Exception as exc:
        log.warning("ld.observe_failed", error=str(exc))


def flush_flinch_events() -> None:
    client = get_client()
    if client is not None:
        try:
            client.flush()
        except Exception as exc:
            log.warning("ld.flush_failed", error=str(exc))
    try:
        from opentelemetry import trace
        from opentelemetry._logs import get_logger_provider
        from opentelemetry.metrics import get_meter_provider

        tracer = trace.get_tracer_provider()
        force_flush = getattr(tracer, "force_flush", None)
        if callable(force_flush):
            force_flush(timeout_millis=10000)
        logger_provider = get_logger_provider()
        log_flush = getattr(logger_provider, "force_flush", None)
        if callable(log_flush):
            log_flush(timeout_millis=10000)
        meters = get_meter_provider()
        meter_flush = getattr(meters, "force_flush", None)
        if callable(meter_flush):
            meter_flush(timeout_millis=10000)
        from ldobserve import observe

        if observe.is_initialized():
            observe.logging_handler().flush()
    except Exception as exc:
        log.warning("ld.observe_flush_failed", error=str(exc))
