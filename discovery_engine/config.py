"""Configuration: .env loader + typed settings.

Keeps secrets out of the repo. Reads discovery_engine/.env or engine/.env,
then lets real environment variables win.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Minimal .env loader — no dependency. Existing env vars win."""
    here = Path(__file__).resolve().parent.parent
    candidates = [here / ".env", here / "discovery_engine" / ".env"]
    for path in candidates:
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_dotenv()

ENGINE_VERSION = "0.1.1"
FINDINGS_SCHEMA = "openendo-discovery-findings-v1"
CLASSIFICATIONS = ("documented-evidence", "likely-association", "untested-hypothesis")
CONFIDENCES = ("high", "medium", "low")
CATEGORIES = ("research_gap", "conflict", "repurposing_lead", "hypothesis")
RAW_BASE = "https://raw.githubusercontent.com/wckdboy/openendo/main"
FETCH_TIMEOUT_SEC = 45
USER_AGENT = f"openendo-discovery-engine/{ENGINE_VERSION}"


@dataclass
class Settings:
    """Resolved settings. Missing optional keys become empty strings."""

    # LangSmith
    langsmith_api_key: str = field(default_factory=lambda: os.environ.get("LANGSMITH_API_KEY", ""))
    langsmith_endpoint: str = field(
        default_factory=lambda: os.environ.get("LANGSMITH_ENDPOINT", "https://eu.api.smith.langchain.com")
    )
    langsmith_project: str = field(
        default_factory=lambda: os.environ.get("LANGSMITH_PROJECT", "openendo-discovery-engine")
    )
    # LLM (OpenAI-compatible)
    openai_base_url: str = field(
        default_factory=lambda: os.environ.get("OPENAI_BASE_URL", "https://api.orcarouter.ai/v1")
    )
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))
    model: str = field(
        default_factory=lambda: os.environ.get("DISCOVERY_MODEL", "deepseek/deepseek-v4-flash-0731")
    )
    temperature: float = field(default_factory=lambda: float(os.environ.get("DISCOVERY_TEMPERATURE", "0.2")))
    # Data source
    source: str = field(default_factory=lambda: os.environ.get("OPENENDO_SOURCE", "raw"))
    local_path: str = field(default_factory=lambda: os.environ.get("OPENENDO_PATH", ""))

    def tracing_enabled(self) -> bool:
        return bool(self.langsmith_api_key)

    def __post_init__(self) -> None:
        if self.source == "local" and not self.local_path:
            raise ValueError("OPENENDO_SOURCE=local requires OPENENDO_PATH to a wckdboy/openendo checkout")
