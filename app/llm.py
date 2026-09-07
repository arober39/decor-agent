from functools import lru_cache

from langchain_anthropic import ChatAnthropic

from app.config import get_settings


def workspace_headers(workspace_id: str) -> dict[str, str] | None:
    """Org API keys must send anthropic-workspace-id. Empty means a scoped key."""
    value = workspace_id.strip()
    if not value:
        return None
    return {"anthropic-workspace-id": value}


@lru_cache(maxsize=32)
def get_llm(model: str, max_tokens: int = 1024, temperature: float = 1.0) -> ChatAnthropic:
    settings = get_settings()
    return ChatAnthropic(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=settings.anthropic_api_key,
        default_headers=workspace_headers(settings.anthropic_workspace_id),
    )
