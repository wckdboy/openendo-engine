"""LangSmith tracing setup.

wrap_openai + @traceable per the langsmith-trace skill. When no
LANGSMITH_API_KEY is present the app still works — tracing simply no-ops.
"""
from __future__ import annotations

import os

from langsmith.wrappers import wrap_openai
from openai import OpenAI

from .config import Settings


def apply_tracing_env(s: Settings) -> None:
    """Make sure the LangSmith SDK sees the right endpoint/project."""
    os.environ.setdefault("LANGSMITH_ENDPOINT", s.langsmith_endpoint)
    os.environ.setdefault("LANGSMITH_PROJECT", s.langsmith_project)
    if s.tracing_enabled():
        os.environ["LANGSMITH_API_KEY"] = s.langsmith_api_key
        os.environ["LANGSMITH_TRACING"] = "true"


def traced_client(s: Settings):
    """OpenAI-compatible client wrapped for auto-tracing."""
    kwargs = {
        "base_url": s.openai_base_url,
        "api_key": s.openai_api_key or "missing",
    }
    return wrap_openai(OpenAI(**kwargs))
