"""LaunchDarkly custom events for the shopping-list loop.

Offline (no SDK key) is a no-op. The store still mutates.
"""

from __future__ import annotations

from typing import Any

from app.flags import build_context, get_client
from app.logging import get_logger

log = get_logger(__name__)

SPEC_SAVED = "spec_saved"
SPEC_APPROVED = "spec_approved"


def track(
    event_key: str,
    context_key: str,
    data: dict[str, Any] | None = None,
    metric_value: float | None = None,
) -> None:
    client = get_client()
    if client is None:
        return
    try:
        context = build_context(context_key)
        client.track(event_key, context, data or {}, metric_value)
    except Exception as exc:
        log.warning("ld.track_failed", event=event_key, error=str(exc))
