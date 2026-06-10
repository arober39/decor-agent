from functools import lru_cache
from langchain_anthropic import ChatAnthropic
from app.config import get_settings


@lru_cache(maxsize=32)
def get_llm(model: str, max_tokens: int = 1024, temperature: float = 1.0) -> ChatAnthropic:
    return ChatAnthropic(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        api_key=get_settings().anthropic_api_key,
    )