"""Shared pytest fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """HTTP client bound to a fresh application instance.

    Used as a context manager so that application startup and shutdown (lifespan) events run,
    exactly as they would in a real server.
    """
    with TestClient(create_app()) as test_client:
        yield test_client
