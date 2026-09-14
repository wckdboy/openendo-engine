"""Default LLM endpoint/model — no network, no API keys."""
from __future__ import annotations

from discovery_engine.config import (
    DEFAULT_DISCOVERY_MODEL,
    DEFAULT_OPENAI_BASE_URL,
    Settings,
)


def test_default_llm_endpoint_is_deepseek_direct(monkeypatch):
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("DISCOVERY_MODEL", raising=False)
    settings = Settings()
    assert DEFAULT_OPENAI_BASE_URL == "https://api.deepseek.com"
    assert DEFAULT_DISCOVERY_MODEL == "deepseek-flash"
    assert settings.openai_base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-flash"


def test_env_overrides_llm_defaults(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.orcarouter.ai/v1")
    monkeypatch.setenv("DISCOVERY_MODEL", "deepseek/deepseek-v4-flash-0731")
    settings = Settings()
    assert settings.openai_base_url == "https://api.orcarouter.ai/v1"
    assert settings.model == "deepseek/deepseek-v4-flash-0731"
