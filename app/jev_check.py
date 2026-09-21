"""Jev flinch check. Stub or TypeSafe. Does not enforce policy."""

from __future__ import annotations

import os
from typing import Protocol

from app.config import get_settings
from app.flags import get_flinch_jev_config

_CHOICES = frozenset({"proceed", "confirm_with_human", "block"})


class JevBackend(Protocol):
    def evaluate(self, state: dict, config: dict) -> dict: ...


class StubJev:
    def evaluate(self, state: dict, config: dict) -> dict:
        return {
            "source": "stub",
            "model": "stub",
            "nouls": {
                "destructive": 0.82,
                "target_shared": 0.91,
                "intent_match": 0.18,
            },
            "action": "confirm_with_human",
            "confidence": 1.0,
            "suggested": "confirm_with_human",
        }


class TypeSafeJev:
    def evaluate(self, state: dict, config: dict) -> dict:
        from typesafe_sdk import TypeSafeClient

        model = (config.get("model") or "jev-1.13.0").strip()
        questions = config.get("questions") or {}
        if not questions:
            raise ValueError("flinch-jev questions are empty")
        key = get_settings().typesafe_api_key.strip()
        with TypeSafeClient(api_key=key or None, model=model) as client:
            response = client.system_one(state=state, questions=questions, model=model)
        nouls = {
            name: float(answer.noul)
            for name, answer in (getattr(response, "nouls", None) or {}).items()
        }
        action = None
        confidence = None
        choices = getattr(response, "choices", None) or {}
        if "action" in choices:
            picked = choices["action"]
            action = getattr(picked, "choice", None)
            confidence = getattr(picked, "confidence", None)
            if confidence is not None:
                confidence = float(confidence)
        answered_model = getattr(response, "model", None) or model
        return {
            "source": "typesafe",
            "model": answered_model,
            "nouls": nouls,
            "action": action,
            "confidence": confidence,
            "suggested": _suggest(action, confidence, config),
        }


def _suggest(action: str | None, confidence: float | None, config: dict) -> str:
    threshold = config.get("choice_confidence_min")
    if not isinstance(threshold, (int, float)):
        threshold = 0.72
    if action not in _CHOICES:
        return "confirm_with_human"
    if confidence is not None and confidence < float(threshold):
        return "confirm_with_human"
    return action


def _pick_backend() -> JevBackend:
    forced = os.environ.get("FLINCH_JEV_BACKEND", "").strip().lower()
    if forced == "stub":
        return StubJev()
    if forced == "typesafe":
        return TypeSafeJev()
    if not get_settings().typesafe_api_key.strip():
        return StubJev()
    return TypeSafeJev()


def evaluate_jev(state: dict, backend: JevBackend | None = None) -> dict:
    config = get_flinch_jev_config(str(state.get("context_key") or "flinch-baseline"))
    try:
        result = (backend or _pick_backend()).evaluate(state, config)
        result.setdefault("suggested", "confirm_with_human")
        return result
    except Exception as exc:
        return {
            "source": "error",
            "model": config.get("model") or "jev-1.13.0",
            "nouls": {},
            "action": None,
            "confidence": None,
            "suggested": "confirm_with_human",
            "error": str(exc),
        }
