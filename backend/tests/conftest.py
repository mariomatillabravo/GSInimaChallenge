"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test independent of the developer's shell environment."""
    for name in ("DEMO_MODE", "AEMET_API_KEY"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    """Demo-mode settings built from explicit values only, never from a local ``.env`` file."""
    return Settings(_env_file=None, demo_mode=True)


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """HTTP client bound to a fresh application instance.

    Used as a context manager so that application startup and shutdown (lifespan) events run,
    exactly as they would in a real server.
    """
    with TestClient(create_app(settings)) as test_client:
        yield test_client
