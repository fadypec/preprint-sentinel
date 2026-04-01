"""Tests for pipeline.config — typed settings from env vars."""


def test_settings_loads_from_env(monkeypatch):
    """Settings reads DATABASE_URL and ANTHROPIC_API_KEY from env."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

    from pipeline.config import Settings

    s = Settings()
    assert s.database_url.get_secret_value() == "postgresql+asyncpg://u:p@localhost/test"
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test-key-12345"


def test_settings_defaults(monkeypatch):
    """Optional fields have sensible defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-key")
    # Clear optional env vars that may exist in the real environment
    monkeypatch.delenv("NCBI_API_KEY", raising=False)

    from pipeline.config import Settings

    s = Settings(_env_file=None)
    assert s.stage1_model == "claude-haiku-4-5-20251001"
    assert s.coarse_filter_threshold == 0.8
    assert s.daily_run_hour == 6
    assert s.biorxiv_request_delay == 1.0
    assert s.ncbi_api_key == ""


def test_secret_str_redacts_in_repr(monkeypatch):
    """SecretStr must never leak in repr/str (logs, tracebacks)."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret")

    from pipeline.config import Settings

    s = Settings()
    assert "sk-ant-super-secret" not in repr(s)
    assert "sk-ant-super-secret" not in str(s.anthropic_api_key)
    # Database URL also protected — password never appears in repr
    assert "u:p@localhost" not in repr(s)


def test_settings_phase2_defaults(monkeypatch):
    """Phase 2 config fields have sensible defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-key")

    from pipeline.config import Settings

    s = Settings()
    assert s.europepmc_request_delay == 1.0
    assert s.pubmed_query_mode == "mesh_filtered"
    assert "virology[MeSH]" in s.pubmed_mesh_query


def test_settings_sp2_defaults(monkeypatch):
    """SP2 config fields have correct defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    from pipeline.config import Settings

    s = Settings()
    assert s.use_batch_api is False
    assert s.unpaywall_request_delay == 0.1
    assert s.fulltext_request_delay == 1.0


def test_settings_sp3_defaults(monkeypatch):
    """SP3 config fields have correct defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")

    from pipeline.config import Settings

    s = Settings()
    assert s.openalex_request_delay == 0.1
    assert s.semantic_scholar_request_delay == 1.0
    assert s.orcid_request_delay == 1.0
    assert s.adjudication_min_tier == "high"
