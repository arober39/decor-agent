from __future__ import annotations
import contextvars
import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

BOARD_INTAKE_FLAG = "decor-board-intake"
FLINCH_POLICY_FLAG = "flinch-policy"
FLINCH_POLICY_DEFAULT = {
    "mode": "live",
    "on_ld_error": "confirm",
    "destructive": {
        "local": "confirm",
        "shared": "block",
    },
}

FLINCH_JEV_FLAG = "flinch-jev"
FLINCH_JEV_DEFAULT = {
    "model": "jev-1.13.0",
    "choice_confidence_min": 0.72,
    "questions": {},
}

_ld_client = None
_ai_client = None

_current_ctx_key: contextvars.ContextVar[str] = contextvars.ContextVar(
    "decor_current_ctx_key", default="anonymous"
)

_current_user_tier: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "decor_current_user_tier", default=None
)


def set_current_context_key(key: str) -> None:
    _current_ctx_key.set(key)


def current_context_key() -> str:
    return _current_ctx_key.get()


def set_current_user_tier(tier: str | None) -> None:
    _current_user_tier.set(tier)


def current_user_tier() -> str | None:
    return _current_user_tier.get()


@dataclass(frozen=True)
class AIConfigDefault:
    """Fallback values used when LD is offline or the config is missing."""
    model: str
    system_prompt: str
    max_tokens: int = 1024
    temperature: float = 1.0


@dataclass
class ResolvedAIConfig:
    """What tools and nodes read. Wraps the LD tracker so callers are vendor-neutral."""
    model: str
    system_prompt: str
    max_tokens: int
    temperature: float
    source: str  # "launchdarkly" | "fallback" | "fallback_error"
    variation: Optional[str] = None
    config_key: Optional[str] = None
    _tracker: Any = None

    def track_success(self) -> None:
        if self._tracker is not None:
            try:
                self._tracker.track_success()
            except Exception as e:
                log.warning("tracker.error", op="success", error=str(e))

    def track_error(self) -> None:
        if self._tracker is not None:
            try:
                self._tracker.track_error()
            except Exception as e:
                log.warning("tracker.error", op="error", error=str(e))

    def track_tokens(self, input_tokens: int, output_tokens: int) -> None:
        if self._tracker is not None:
            try:
                from ldai.tracker import TokenUsage

                self._tracker.track_tokens(
                    TokenUsage(
                        input=input_tokens,
                        output=output_tokens,
                        total=input_tokens + output_tokens,
                    )
                )
            except Exception as e:
                log.warning("tracker.error", op="tokens", error=str(e))

    def track_duration(self, duration_ms: int) -> None:
        if self._tracker is not None:
            try:
                self._tracker.track_duration(duration_ms)
            except Exception as e:
                log.warning("tracker.error", op="duration", error=str(e))


def _keep_otel_auto_instrumentation_alive() -> None:
    """One failed library wrap must not abort the rest of OTEL auto-init."""
    from opentelemetry.instrumentation.dependencies import DependencyConflictError
    from opentelemetry.instrumentation.distro import BaseDistro

    if getattr(BaseDistro.load_instrumentor, "_decor_resilient", False):
        return
    original = BaseDistro.load_instrumentor

    def load_instrumentor(self, entry_point, **kwargs):
        try:
            return original(self, entry_point, **kwargs)
        except (DependencyConflictError, ModuleNotFoundError, ImportError):
            raise
        except Exception as exc:
            log.warning(
                "otel.instrumentor_failed",
                name=getattr(entry_point, "name", None),
                error=str(exc),
            )

    load_instrumentor._decor_resilient = True  # type: ignore[attr-defined]
    BaseDistro.load_instrumentor = load_instrumentor


def _attach_observe_log_handler() -> None:
    """Export stdlib logs to Observe without LoggingInstrumentor (keeps structlog)."""
    try:
        from ldobserve import observe
        from ldobserve._otel.logging_handler import install_on_root_logger

        if not observe.is_initialized():
            return
        handler = observe.logging_handler()
        if handler is None or isinstance(handler, logging.NullHandler):
            return
        # record_log uses logging.getLogger("ldobserve.observe"). Root defaults
        # to WARNING, so INFO records never reached the OTEL handler (traces
        # still worked; they do not go through stdlib logging).
        observe_logger = logging.getLogger("ldobserve.observe")
        observe_logger.setLevel(logging.DEBUG)
        observe_logger.propagate = False
        install_on_root_logger(handler)
    except Exception as exc:
        log.warning("ld.observe_log_handler_failed", error=str(exc))


def init_client() -> None:
    global _ld_client, _ai_client
    settings = get_settings()
    if not settings.ld_sdk_key:
        log.warning("launchdarkly.offline_mode", reason="LD_SDK_KEY not set")
        return
    try:
        import ldclient
        from ldclient.config import Config as LDClientConfig
        from ldai.client import LDAIClient
    except ImportError as e:
        log.error("launchdarkly.sdk_not_installed", error=str(e))
        return
    try:
        plugins = []
        try:
            from ldobserve import ObservabilityConfig, ObservabilityPlugin

            # Entry point is qdrant_client, not qdrant. Skip only that wrap;
            # other auto-instrumentors stay on for Observability traces.
            skipped = "qdrant_client"
            existing = [
                name.strip()
                for name in os.environ.get(
                    "OTEL_PYTHON_DISABLED_INSTRUMENTATIONS", ""
                ).split(",")
                if name.strip()
            ]
            if skipped not in existing:
                existing.append(skipped)
            os.environ["OTEL_PYTHON_DISABLED_INSTRUMENTATIONS"] = ",".join(
                existing
            )
            _keep_otel_auto_instrumentation_alive()
            plugins.append(
                ObservabilityPlugin(
                    ObservabilityConfig(
                        service_name="decor-agent",
                        environment=settings.environment,
                        instrument_logging=False,
                        disabled_instrumentations=[skipped],
                    )
                )
            )
        except Exception as plugin_error:
            log.warning("launchdarkly.observability_skipped", error=str(plugin_error))
        ldclient.set_config(
            LDClientConfig(settings.ld_sdk_key, plugins=plugins or None)
        )
        _ld_client = ldclient.get()
        _ai_client = LDAIClient(_ld_client)
        if plugins:
            _attach_observe_log_handler()
        log.info("launchdarkly.initialized", observability=bool(plugins))
    except Exception as e:
        log.error("launchdarkly.init_failed", error=str(e))


def close_client() -> None:
    global _ld_client, _ai_client
    if _ld_client is not None:
        try:
            _ld_client.close()
        except Exception as e:
            log.warning("launchdarkly.close_error", error=str(e))
    _ld_client = None
    _ai_client = None


def get_client():
    return _ld_client


def build_context(context_key: str, **attrs):
    """Build an LD Context, or a dict-like stand-in for offline mode."""
    if _ai_client is None:
        return {"key": context_key, **attrs}
    from ldclient import Context
    builder = Context.builder(context_key).kind("user")
    if "user-tier" not in attrs:
        explicit = current_user_tier()
        if explicit:
            attrs["user-tier"] = explicit
        elif context_key.startswith("premium-"):
            attrs["user-tier"] = "premium"
        elif context_key.startswith("free-"):
            attrs["user-tier"] = "free"
        else:
            attrs["user-tier"] = "free"
    for k, v in attrs.items():
        builder.set(k, v)
    return builder.build()


def get_flag(key: str, context, default: bool = False) -> bool:
    if _ld_client is None:
        return default
    try:
        return _ld_client.variation(key, context, default)
    except Exception as e:
        log.error("flag.error", key=key, error=str(e))
        return default


def get_json_flag(key: str, context, default: dict) -> dict:
    if _ld_client is None:
        return default
    try:
        value = _ld_client.variation(key, context, default)
    except Exception as e:
        log.error("flag.error", key=key, error=str(e))
        return default
    if isinstance(value, dict):
        return value
    return default


def _merge_flinch_policy(policy: dict) -> dict:
    destructive = {
        **FLINCH_POLICY_DEFAULT["destructive"],
        **(policy.get("destructive") or {}),
    }
    if destructive.get("shared") == "allow":
        destructive["shared"] = "confirm"
    return {
        "mode": policy.get("mode") or FLINCH_POLICY_DEFAULT["mode"],
        "on_ld_error": policy.get("on_ld_error") or FLINCH_POLICY_DEFAULT["on_ld_error"],
        "destructive": destructive,
    }


def get_flinch_policy(context_key: str = "flinch-baseline", **attrs) -> dict:
    """Evaluate flinch-policy. Offline or malformed JSON returns fail-closed."""
    context = build_context(context_key, **attrs)
    if _ld_client is None:
        return dict(FLINCH_POLICY_DEFAULT)
    raw = get_json_flag(FLINCH_POLICY_FLAG, context, FLINCH_POLICY_DEFAULT)
    return _merge_flinch_policy(raw)


def _merge_flinch_jev_config(config: dict) -> dict:
    model = (config.get("model") or FLINCH_JEV_DEFAULT["model"]).strip()
    if not model:
        model = FLINCH_JEV_DEFAULT["model"]
    threshold = config.get("choice_confidence_min")
    if not isinstance(threshold, (int, float)):
        threshold = FLINCH_JEV_DEFAULT["choice_confidence_min"]
    questions = config.get("questions")
    if not isinstance(questions, dict):
        questions = dict(FLINCH_JEV_DEFAULT["questions"])
    return {
        "model": model,
        "choice_confidence_min": float(threshold),
        "questions": questions,
    }


def get_flinch_jev_config(context_key: str = "flinch-baseline", **attrs) -> dict:
    """Evaluate flinch-jev. Offline or malformed JSON returns the pinned model."""
    context = build_context(context_key, **attrs)
    if _ld_client is None:
        return dict(FLINCH_JEV_DEFAULT)
    raw = get_json_flag(FLINCH_JEV_FLAG, context, FLINCH_JEV_DEFAULT)
    return _merge_flinch_jev_config(raw)


def get_completion_config(
    config_key: str,
    context,
    default: AIConfigDefault,
) -> ResolvedAIConfig:
    if _ai_client is None:
        log.debug("ai_config.offline", config_key=config_key)
        return ResolvedAIConfig(
            model=default.model,
            system_prompt=default.system_prompt,
            max_tokens=default.max_tokens,
            temperature=default.temperature,
            source="fallback",
            config_key=config_key,
        )
    try:
        from ldai.client import AICompletionConfigDefault, ModelConfig, LDMessage
        ld_default = AICompletionConfigDefault(
            enabled=True,
            model=ModelConfig(
                name=default.model,
                parameters={
                    "max_tokens": default.max_tokens,
                    "temperature": default.temperature,
                },
            ),
            messages=[LDMessage(role="system", content=default.system_prompt)],
        )
        cfg = _ai_client.completion_config(config_key, context, ld_default)

        system_prompt = default.system_prompt
        for msg in cfg.messages or []:
            if msg.role == "system":
                system_prompt = msg.content
                break

        if cfg.model is None:
            model_name = default.model
            max_tokens = default.max_tokens
            temperature = default.temperature
            log.warning(
                "ai_config.model_missing",
                config_key=config_key,
                hint="AI Config variation has no model set; using default model but LD prompt",
            )
        else:
            model_name = cfg.model.name
            max_tokens = cfg.model.get_parameter("max_tokens") or default.max_tokens
            temperature = cfg.model.get_parameter("temperature")
            if temperature is None:
                temperature = default.temperature

        variation = getattr(cfg, "variation_key", None) or getattr(cfg, "variation", None)

        log.info(
            "ai_config.fetched",
            config_key=config_key,
            source="launchdarkly",
            model=model_name,
            variation=variation,
        )
        return ResolvedAIConfig(
            model=model_name,
            system_prompt=system_prompt,
            max_tokens=int(max_tokens),
            temperature=float(temperature),
            source="launchdarkly",
            variation=variation,
            config_key=config_key,
            _tracker=cfg.tracker,
        )
    except Exception as e:
        log.error("ai_config.fetch_failed", config_key=config_key, error=str(e))
        return ResolvedAIConfig(
            model=default.model,
            system_prompt=default.system_prompt,
            max_tokens=default.max_tokens,
            temperature=default.temperature,
            source="fallback_error",
            config_key=config_key,
        )