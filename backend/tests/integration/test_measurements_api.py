"""Integration tests for the measurements endpoint, through the whole HTTP stack.

The weather source is replaced by an in-memory fake through ``dependency_overrides``.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_measurement_service
from app.core.config import Settings
from app.core.exceptions import UpstreamError, UpstreamTimeoutError, UpstreamUnavailableError
from app.domain.measurements import Observation
from app.domain.stations import Station
from app.main import create_app
from app.services.measurements import MeasurementService

URL = "/api/v1/stations/juan-carlos-i/measurements"


class FakeWeatherSource:
    """In-memory ``WeatherSource``: serves the observations it holds, or raises ``error``."""

    def __init__(self) -> None:
        self.observations: list[Observation] = []
        self.error: Exception | None = None
        self.calls: list[tuple[str, datetime, datetime]] = []

    def fetch(self, station: Station, start: datetime, end: datetime) -> list[Observation]:
        self.calls.append((station.aemet_id, start, end))
        if self.error is not None:
            raise self.error
        return [obs for obs in self.observations if start <= obs.timestamp <= end]


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def grid(start: str, count: int, temperature: float | None = 1.0) -> list[Observation]:
    first = utc(start)
    return [
        Observation(first + timedelta(minutes=10 * step), temperature, 980.0, 5.0)
        for step in range(count)
    ]


@pytest.fixture
def source() -> FakeWeatherSource:
    return FakeWeatherSource()


@pytest.fixture
def api(settings: Settings, source: FakeWeatherSource) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_measurement_service] = lambda: MeasurementService(source, "demo")
    with TestClient(app) as client:
        yield client


def get_ok(api: TestClient, **params: Any) -> dict[str, Any]:
    response = api.get(URL, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


class TestRawSeries:
    def test_madrid_input_and_output_with_all_types(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T00:00:00", 3)

        body = get_ok(api, start="2026-01-15T01:00:00", end="2026-01-15T01:20:00")

        assert body["metadata"] == {
            "station": {
                "id": "juan-carlos-i",
                "name": "Juan Carlos I",
                "aemet_id": "89064",
                "aemet_name": "JCI Estacion meteorologica",
            },
            "aggregation": "none",
            "start": "2026-01-15T01:00:00+01:00",
            "end": "2026-01-15T01:20:00+01:00",
            "input_interpretation": "Europe/Madrid (default)",
            "output_timezone": "Europe/Madrid",
            "station_timezone": "UTC-03:00",
            "source": "demo",
            "count": 3,
        }
        assert body["data"][0] == {
            "station": "Juan Carlos I",
            "datetime": "2026-01-15T01:00:00+01:00",
            "temperature_c": 1.0,
            "pressure_hpa": 980.0,
            "speed_ms": 5.0,
        }
        assert list(body["fields"]) == [
            "station", "datetime", "temperature_c", "pressure_hpa", "speed_ms",
        ]  # fmt: skip
        assert body["fields"]["temperature_c"] == {"label": "Temperature (°C)", "unit": "°C"}

    def test_the_source_receives_the_range_in_utc(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        get_ok(api, start="2026-07-15T00:00:00", end="2026-07-16T00:00:00")

        assert source.calls == [("89064", utc("2026-07-14T22:00:00"), utc("2026-07-15T22:00:00"))]

    def test_only_requested_types_are_returned(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T00:00:00", 1)

        body = get_ok(api, start="2026-01-15T00:00:00Z", end="2026-01-15T00:10:00Z", types="speed")

        assert body["data"] == [
            {"station": "Juan Carlos I", "datetime": "2026-01-15T01:00:00+01:00", "speed_ms": 5.0}
        ]

    def test_types_can_be_comma_separated_and_repeated(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T00:00:00", 1)

        response = api.get(
            URL,
            params=[
                ("start", "2026-01-15T00:00:00Z"),
                ("end", "2026-01-15T00:10:00Z"),
                ("types", "speed, temperature"),
                ("types", "speed"),
            ],
        )

        assert list(response.json()["fields"]) == [
            "station",
            "datetime",
            "temperature_c",
            "speed_ms",
        ]

    def test_missing_values_are_explicit_nulls(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T00:00:00", 1, temperature=None)

        body = get_ok(api, start="2026-01-15T00:00:00Z", end="2026-01-15T00:10:00Z")

        assert body["data"][0]["temperature_c"] is None

    def test_offset_with_plus_sign_written_raw_in_the_url(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-14T22:00:00", 1)

        response = api.get(f"{URL}?start=2026-01-15T00:00:00&end=2026-01-15T01:00:00&tz=+02:00")

        assert response.json()["metadata"]["input_interpretation"] == "+02:00 (tz parameter)"
        assert response.json()["metadata"]["count"] == 1


class TestAggregatedSeries:
    def test_daily_rows_carry_period_and_quality_fields(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 144)

        body = get_ok(
            api, start="2026-01-15T03:00:00Z", end="2026-01-16T02:50:00Z", aggregation="daily"
        )

        assert body["data"] == [
            {
                "station": "Juan Carlos I",
                "datetime": "2026-01-15T04:00:00+01:00",
                "period": "2026-01-15",
                "temperature_c": 1.0,
                "pressure_hpa": 980.0,
                "speed_ms": 5.0,
                "samples": 144,
                "expected_samples": 144,
                "coverage": 100.0,
            }
        ]
        assert body["fields"]["coverage"] == {"label": "Coverage (%)", "unit": "%"}
        assert body["fields"]["period"] == {"label": "Period", "unit": None}

    def test_hourly_rows_have_no_period(self, api: TestClient, source: FakeWeatherSource) -> None:
        source.observations = grid("2026-01-15T10:00:00", 6)

        body = get_ok(
            api, start="2026-01-15T10:00:00Z", end="2026-01-15T10:50:00Z", aggregation="hourly"
        )

        assert "period" not in body["data"][0]
        assert "period" not in body["fields"]

    def test_means_are_rounded_to_two_decimals(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = [
            *grid("2026-01-15T10:00:00", 1, temperature=1.0),
            *grid("2026-01-15T10:10:00", 2, temperature=2.0),
        ]

        body = get_ok(
            api, start="2026-01-15T10:00:00Z", end="2026-01-15T10:59:00Z", aggregation="hourly"
        )

        assert body["data"][0]["temperature_c"] == 1.67


class TestErrors:
    def test_unknown_station(self, api: TestClient) -> None:
        response = api.get(
            "/api/v1/stations/89064/measurements",
            params={"start": "2026-01-15T00:00:00", "end": "2026-01-16T00:00:00"},
        )

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
        assert "juan-carlos-i" in response.json()["error"]["message"]

    @pytest.mark.parametrize(
        ("params", "parameter", "fragment"),
        [
            (
                {"start": "15/01/2026", "end": "2026-01-16T00:00:00"},
                "start",
                "not a valid datetime",
            ),
            ({"start": "2026-10-25T02:30:00", "end": "2026-10-26T00:00:00"}, "start", "ambiguous"),
            (
                {"start": "2026-03-29T02:30:00", "end": "2026-03-30T00:00:00"},
                "start",
                "does not exist",
            ),
            ({"start": "2026-01-15T00:00:00"}, "end", "Field required"),
            (
                {
                    "start": "2026-01-15T00:00:00",
                    "end": "2026-01-16T00:00:00",
                    "aggregation": "weekly",
                },
                "aggregation",
                "Input should be",
            ),
            (
                {"start": "2026-01-15T00:00:00", "end": "2026-01-16T00:00:00", "types": "humidity"},
                "types",
                "Unknown measurement type",
            ),
            (
                {"start": "2026-01-01T00:00:00", "end": "2026-03-01T00:00:00"},
                "end",
                "longer than 31 days",
            ),
            (
                {"start": "2026-01-15T00:00:00", "end": "2026-01-16T00:00:00", "tz": "Mars/Base"},
                "tz",
                "neither an IANA",
            ),
        ],
    )
    def test_invalid_parameters_get_a_uniform_422(
        self, api: TestClient, params: dict[str, str], parameter: str, fragment: str
    ) -> None:
        response = api.get(URL, params=params)

        assert response.status_code == 422
        error = response.json()["error"]
        assert (error["code"], error["parameter"]) == ("invalid_parameter", parameter)
        assert fragment in error["message"]

    @pytest.mark.parametrize(
        ("error", "status_code", "code"),
        [
            (UpstreamUnavailableError("AEMET could not be reached."), 503, "upstream_unavailable"),
            (UpstreamTimeoutError("AEMET did not answer in time."), 504, "upstream_timeout"),
            (UpstreamError("AEMET rejected the API key."), 502, "upstream_error"),
        ],
    )
    def test_upstream_failures_map_to_gateway_statuses(
        self,
        api: TestClient,
        source: FakeWeatherSource,
        error: Exception,
        status_code: int,
        code: str,
    ) -> None:
        source.error = error

        response = api.get(
            URL, params={"start": "2026-01-15T00:00:00", "end": "2026-01-16T00:00:00"}
        )

        assert response.status_code == status_code
        assert response.json() == {
            "error": {"code": code, "message": str(error), "parameter": None}
        }

    def test_unexpected_errors_do_not_leak_details(
        self, settings: Settings, source: FakeWeatherSource
    ) -> None:
        source.error = RuntimeError("database password is hunter2")
        app = create_app(settings)
        app.dependency_overrides[get_measurement_service] = lambda: MeasurementService(
            source, "demo"
        )

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                URL, params={"start": "2026-01-15T00:00:00", "end": "2026-01-16T00:00:00"}
            )

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "hunter2" not in response.text
