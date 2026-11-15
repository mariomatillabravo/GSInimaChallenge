"""Shared pytest fixtures."""

import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

ConcurrentRunner = Callable[[int, Callable[[int], None]], list[BaseException]]


@pytest.fixture(autouse=True)
def _isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep every test independent of the developer's shell environment and local files."""
    for name in ("DEMO_MODE", "AEMET_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    # Applications built by tests keep their cache in a temporary file, never in backend/data.
    monkeypatch.setenv("CACHE_DB_PATH", str(tmp_path / "cache.sqlite3"))


@pytest.fixture
def run_concurrently() -> ConcurrentRunner:
    """Return a helper that runs ``target(index)`` in ``count`` threads released at once.

    A barrier holds every thread until all of them are ready, which makes races far more likely
    than starting the threads one after another. The helper returns the exceptions raised.
    """

    def run(count: int, target: Callable[[int], None]) -> list[BaseException]:
        barrier = threading.Barrier(count)
        errors: list[BaseException] = []

        def worker(index: int) -> None:
            barrier.wait()
            try:
                target(index)
            except BaseException as error:
                errors.append(error)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return errors

    return run


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
