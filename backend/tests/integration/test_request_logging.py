"""Request IDs and logs through the whole application, with the log output captured as JSON."""

import io
import json
import logging
import re
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.logs import configure_logging
from app.main import create_app

FIXTURES = Path(__file__).parents[1] / "fixtures" / "aemet"
DAY = FIXTURES / "data_89064_2026-01-15_2026-01-16.json"
URL = "/api/v1/stations/juan-carlos-i/measurements"
PARAMS = {"start": "2026-01-15T03:00:00Z", "end": "2026-01-15T04:00:00Z"}
HEX_32 = re.compile(r"[0-9a-f]{32}")
API_KEY = "secret-key-that-must-never-be-logged"


class LogCapture:
    def __init__(self) -> None:
        self.stream = io.StringIO()

    def entries(self) -> list[dict[str, object]]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]

    def for_request(self, request_id: str) -> list[dict[str, object]]:
        return [entry for entry in self.entries() if entry["request_id"] == request_id]


def start(app: FastAPI, logs: LogCapture, level: str = "INFO") -> TestClient:
    # create_app configured logging to standard error; send it to the capture instead.
    configure_logging("DEBUG" if level == "DEBUG" else "INFO", "json", stream=logs.stream)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def logs() -> LogCapture:
    return LogCapture()


@pytest.fixture
def demo_app(tmp_path: Path) -> FastAPI:
    shutil.copy(DAY, tmp_path / "89064_2026-01.json")
    app = create_app(Settings(_env_file=None, demo_mode=True, demo_data_dir=tmp_path))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("unexpected failure")

    return app


@pytest.fixture
def api(demo_app: FastAPI, logs: LogCapture) -> Iterator[TestClient]:
    with start(demo_app, logs) as client:
        yield client


def test_every_response_carries_a_new_request_id(api: TestClient) -> None:
    first = api.get("/health").headers["X-Request-ID"]
    second = api.get("/health").headers["X-Request-ID"]

    assert HEX_32.fullmatch(first)
    assert first != second


def test_a_safe_request_id_from_the_client_is_kept(api: TestClient) -> None:
    response = api.get("/health", headers={"X-Request-ID": "front-42.retry_1"})

    assert response.headers["X-Request-ID"] == "front-42.retry_1"


def test_an_unsafe_request_id_from_the_client_is_replaced(api: TestClient) -> None:
    response = api.get("/health", headers={"X-Request-ID": "<script>alert(1)</script>"})

    assert HEX_32.fullmatch(response.headers["X-Request-ID"])


@pytest.mark.parametrize(
    ("path", "params", "status"),
    [
        ("/api/v1/stations/unknown/measurements", PARAMS, 404),
        (URL, {"start": "not-a-date", "end": "2026-01-15T04:00:00Z"}, 422),
        ("/boom", {}, 500),
    ],
)
def test_error_responses_carry_the_request_id(
    api: TestClient, path: str, params: dict[str, str], status: int
) -> None:
    response = api.get(path, params=params)

    assert response.status_code == status
    assert HEX_32.fullmatch(response.headers["X-Request-ID"])


def test_an_unexpected_error_is_logged_with_its_traceback_and_request_id(
    api: TestClient, logs: LogCapture
) -> None:
    request_id = api.get("/boom").headers["X-Request-ID"]

    errors = [entry for entry in logs.for_request(request_id) if entry["level"] == "ERROR"]
    assert len(errors) == 1
    assert "RuntimeError: unexpected failure" in str(errors[0]["exception"])


def test_logs_written_by_the_endpoint_thread_carry_the_request_id(
    api: TestClient, logs: LogCapture
) -> None:
    # The endpoint runs in a worker thread; the service logs the fetch from there.
    request_id = api.get(URL, params=PARAMS).headers["X-Request-ID"]

    messages = [entry["message"] for entry in logs.for_request(request_id)]
    assert any(
        str(message).startswith("Fetched juan-carlos-i 2026-01 from demo") for message in messages
    )


def test_one_access_line_is_written_per_request(api: TestClient, logs: LogCapture) -> None:
    request_id = api.get(URL, params=PARAMS).headers["X-Request-ID"]

    access = [entry for entry in logs.for_request(request_id) if entry["logger"] == "app.access"]
    assert len(access) == 1
    http = access[0]["http"]
    assert isinstance(http, dict)
    assert (http["method"], http["path"], http["status"]) == ("GET", URL, 200)
    assert "start=2026-01-15T03" in str(http["query"])
    assert isinstance(http["duration_ms"], float)


def test_the_api_key_never_appears_in_the_logs(
    logs: LogCapture, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_url = "https://aemet.test/opendata"
    settings = Settings(_env_file=None, aemet_api_key=API_KEY, aemet_base_url=base_url)
    app = create_app(settings)
    envelope = {"descripcion": "exito", "estado": 200, "datos": f"{base_url}/sh/day"}
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        january = router.get(url__startswith=f"{base_url}/api/antartida/datos/fechaini/2026-01")
        january.respond(200, content=json.dumps(envelope))
        router.get(f"{base_url}/sh/day").respond(
            200,
            content=DAY.read_bytes(),
            headers={"content-type": "text/plain;charset=ISO-8859-15"},
        )
        # A rejected key for another month, so that the error path is logged too.
        router.get(url__startswith=f"{base_url}/api/antartida/datos/fechaini/2025-01").respond(401)
        with start(app, logs, level="DEBUG") as client:
            # Even the HTTP libraries' own debug output, normally silenced, must not show it.
            for name in ("httpx", "httpcore"):
                monkeypatch.setattr(logging.getLogger(name), "level", logging.DEBUG)
            ok = client.get(URL, params=PARAMS)
            rejected = client.get(
                URL, params={"start": "2025-01-15T00:00:00Z", "end": "2025-01-16T00:00:00Z"}
            )

    assert (ok.status_code, rejected.status_code) == (200, 502)
    loggers = {entry["logger"] for entry in logs.entries()}
    # The capture really holds the upstream URLs (httpx), the failure and the access lines.
    assert {"httpx", "app.services.circuit", "app.access"} <= loggers
    assert API_KEY not in logs.stream.getvalue()
