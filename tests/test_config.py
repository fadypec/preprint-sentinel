"""Tests for pipeline.config — typed settings from env vars."""

import os

from pydantic import SecretStr


def test_settings_loads_from_env(monkeypatch):
    """Settings reads DATABASE_URL and ANTHROPIC_API_KEY from env."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-12345")

    from pipeline.config import Settings

    s = Settings()
    assert s.database_url == "postgresql+asyncpg://u:p@localhost/test"
    assert s.anthropic_api_key.get_secret_value() == "sk-ant-test-key-12345"


def test_settings_defaults(monkeypatch):
    """Optional fields have sensible defaults."""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@localhost/test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-key")

    from pipeline.config import Settings

    s = Settings()
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
