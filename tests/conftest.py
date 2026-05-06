"""Pytest fixtures wspólne dla całego testowego zestawu."""

import os
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def env_loaded(repo_root: Path) -> None:
    """Smoke testom potrzebny .env. Pomija test jeśli brak."""
    env_path = repo_root / ".env"
    if not env_path.exists():
        pytest.skip(".env not present — skip end-to-end smoke")
    from dotenv import load_dotenv
    load_dotenv(env_path)
    if not os.environ.get("LUXMED_EMAIL"):
        pytest.skip("LUXMED_EMAIL nie ustawiony")
