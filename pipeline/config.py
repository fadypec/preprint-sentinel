"""Typed configuration loaded from environment variables.

All API keys use SecretStr so they are never logged or printed in tracebacks.
Instantiate via get_settings() for a cached singleton.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Database
    database_url: str

    # Anthropic
    anthropic_api_key: SecretStr

    # External APIs (free, email-based auth)
    ncbi_api_key: str = ""
    unpaywall_email: str = ""
    openalex_email: str = ""
    semantic_scholar_api_key: SecretStr = SecretStr("")

    # Model selection
    stage1_model: str = "claude-haiku-4-5-20251001"
    stage2_model: str = "claude-sonnet-4-6"
    stage3_model: str = "claude-opus-4-6"

    # Pipeline tuning
    coarse_filter_threshold: float = 0.8
    daily_run_hour: int = 6

    # Rate limits (seconds between requests)
    biorxiv_request_delay: float = 1.0
    pubmed_request_delay: float = 0.1


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
