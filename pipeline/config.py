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
    database_url: SecretStr

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
    use_batch_api: bool = False

    # Rate limits (seconds between requests)
    biorxiv_request_delay: float = 1.0
    pubmed_request_delay: float = 0.1
    europepmc_request_delay: float = 1.0
    unpaywall_request_delay: float = 0.1
    fulltext_request_delay: float = 1.0

    # PubMed query mode
    pubmed_query_mode: str = "mesh_filtered"  # "all" or "mesh_filtered"
    pubmed_mesh_query: str = (
        '(virology[MeSH] OR microbiology[MeSH] OR "synthetic biology"[MeSH] OR '
        '"genetic engineering"[MeSH] OR "gain of function"[tiab] OR '
        '"gain-of-function"[tiab] OR "directed evolution"[tiab] OR '
        '"reverse genetics"[tiab] OR "gene drive"[tiab] OR "gene drives"[tiab] OR '
        '"select agent"[tiab] OR "select agents"[tiab] OR '
        '"dual use"[tiab] OR "dual-use"[tiab] OR '
        '"pathogen enhancement"[tiab] OR "immune evasion"[tiab] OR '
        '"host range"[tiab] OR "transmissibility"[tiab] OR '
        '"virulence factor"[tiab] OR "virulence factors"[tiab] OR '
        'toxins[MeSH] OR "biological warfare"[MeSH] OR "biodefense"[MeSH] OR '
        'CRISPR[tiab] OR "base editing"[tiab] OR '
        '"pandemic preparedness"[tiab] OR "pandemic pathogen"[tiab] OR '
        '"biosafety level"[tiab] OR "BSL-3"[tiab] OR "BSL-4"[tiab] OR '
        'prions[MeSH] OR "mirror life"[tiab] OR "xenobiology"[tiab] OR '
        '"de novo protein design"[tiab] OR "protein design"[tiab] OR '
        '"aerosol transmission"[tiab] OR "airborne transmission"[tiab])'
    )

    # Enrichment rate limits
    openalex_request_delay: float = 0.1
    semantic_scholar_request_delay: float = 1.0
    orcid_request_delay: float = 1.0

    # Adjudication
    adjudication_min_tier: str = "high"  # "low", "medium", "high", "critical"


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
