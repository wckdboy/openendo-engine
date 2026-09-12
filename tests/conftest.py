"""Pytest fixtures wrapping the synthetic helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from discovery_engine.data import Corpus
from tests.helpers import mini_corpus, write_mini_openendo


@pytest.fixture
def fixture_corpus() -> Corpus:
    return mini_corpus()


@pytest.fixture
def local_openendo(tmp_path: Path) -> Path:
    return write_mini_openendo(tmp_path / "openendo")
