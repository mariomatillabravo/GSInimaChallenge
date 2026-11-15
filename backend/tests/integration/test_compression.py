"""Integration tests for response compression."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parents[1] / "fixtures" / "aemet"
RAW_DAY = (
    "/api/v1/stations/juan-carlos-i/measurements"
    "?start=2026-01-15T00:00:00Z&end=2026-01-16T00:00:00Z"
)


@pytest.fixture
def demo_client(tmp_path: Path) -> Iterator[TestClient]:
    shutil.copy(FIXTURES / "data_89064_2026-01-15_2026-01-16.json", tmp_path / "89064_2026-01.json")
    settings = Settings(_env_file=None, demo_mode=True, demo_data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        yield client


def test_large_responses_are_gzip_compressed(demo_client: TestClient) -> None:
    response = demo_client.get(RAW_DAY, headers={"Accept-Encoding": "gzip"})

    assert response.headers["content-encoding"] == "gzip"
    assert response.json()["metadata"]["count"] == 145  # the client decompresses transparently


def test_clients_that_do_not_accept_gzip_get_plain_responses(demo_client: TestClient) -> None:
    response = demo_client.get(RAW_DAY, headers={"Accept-Encoding": "identity"})

    assert "content-encoding" not in response.headers


def test_small_responses_are_not_compressed(demo_client: TestClient) -> None:
    response = demo_client.get("/health", headers={"Accept-Encoding": "gzip"})

    assert "content-encoding" not in response.headers
