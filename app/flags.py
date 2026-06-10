from __future__ import annotations
import contextvars
from dataclasses import dataclass
from typing import Any, Optional

from app.config import get_settings
from app.logging import get_logger

log = get_logger(__name__)

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
        ldclient.set_config(LDClientConfig(settings.ld_sdk_key))
        _ld_client = ldclient.get()
        _ai_client = LDAIClient(_ld_client)
        log.info("launchdarkly.initialized")
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