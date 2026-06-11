from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    anthropic_api_key: str = Field(validation_alias="ANTHROPIC_API_KEY")
    ld_sdk_key: str = Field(default="", validation_alias="LD_SDK_KEY")
    ld_api_token: str = Field(default="", validation_alias="LAUNCHDARKLY_API_TOKEN")
    ld_project_key: str = Field(
        default="",
        validation_alias=AliasChoices("LAUNCHDARKLY_PROJECT_KEY", "LD_PROJECT_KEY"),
    )
    ld_project_name: str = Field(default="", validation_alias="LAUNCHDARKLY_PROJECT_NAME")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")

    default_model: str = "claude-sonnet-4-20250514"
    fallback_model: str = "claude-3-5-sonnet-20241022"
    max_tokens: int = 1024
    max_input_length: int = 2000
    max_retries: int = 2


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
