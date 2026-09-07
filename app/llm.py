from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from app.config import get_settings

# Sonnet 5 / Opus 5 / Fable reject non-default temperature and manual thinking.
_NO_SAMPLING_PREFIXES = (
    "claude-sonnet-5",
    "claude-opus-5",
    "claude-fable-5",
)


def workspace_headers(workspace_id: str) -> dict[str, str] | None:
    """Org API keys must send anthropic-workspace-id. Empty means a scoped key."""
    value = workspace_id.strip()
    if not value:
        return None
    return {"anthropic-workspace-id": value}


def rejects_sampling(model: str) -> bool:
    return any(model.startswith(prefix) for prefix in _NO_SAMPLING_PREFIXES)


def chat_kwargs(
    model: str,
    max_tokens: int,
    temperature: float,
    api_key: str,
    workspace_id: str,
) -> dict:
    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "api_key": api_key,
        "default_headers": workspace_headers(workspace_id),
    }
    if rejects_sampling(model):
        kwargs["thinking"] = {"type": "disabled"}
    else:
        kwargs["temperature"] = temperature
    return kwargs


@lru_cache(maxsize=32)
def get_llm(model: str, max_tokens: int = 1024, temperature: float = 1.0) -> ChatAnthropic:
    settings = get_settings()
    return ChatAnthropic(
        **chat_kwargs(
            model,
            max_tokens,
            temperature,
            settings.anthropic_api_key,
            settings.anthropic_workspace_id,
        )
    )
