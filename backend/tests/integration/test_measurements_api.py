"""Integration tests for the measurements endpoint, through the whole HTTP stack.

The weather source is replaced by an in-memory fake through ``dependency_overrides``; the cache
is a real SQLite file and the clock is fixed.
"""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.dependencies import get_measurement_service
from app.core.config import Settings
from app.core.exceptions import UpstreamError, UpstreamTimeoutError, UpstreamUnavailableError
from app.db.database import open_database
from app.db.repository import CacheRepository
from app.domain.freshness import FreshnessPolicy
from app.domain.measurements import Observation
from app.domain.stations import Station
from app.main import create_app
from app.services.measurements import MeasurementService, SourceLabel

URL = "/api/v1/stations/juan-carlos-i/measurements"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
POLICY = FreshnessPolicy(ttl=timedelta(hours=1), grace=timedelta(hours=48))


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


ServiceFactory = Callable[[FakeWeatherSource, SourceLabel], MeasurementService]


class FakeClock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def source() -> FakeWeatherSource:
    return FakeWeatherSource()


@pytest.fixture
def make_service(tmp_path: Path, clock: FakeClock) -> Iterator[ServiceFactory]:
    """Build a service over a source, with its own cache file and a clock that starts at ``NOW``."""
    engines: list[Engine] = []

    def make(source: FakeWeatherSource, label: SourceLabel) -> MeasurementService:
        engine = open_database(tmp_path / f"service-{label}.sqlite3", data_source=label)
        engines.append(engine)
        return MeasurementService(source, label, CacheRepository(engine), POLICY, clock=clock)

    yield make
    for engine in engines:
        engine.dispose()


@pytest.fixture
def api(
    settings: Settings, source: FakeWeatherSource, make_service: ServiceFactory
) -> Iterator[TestClient]:
    app = create_app(settings)
    service = make_service(source, "demo")
    app.dependency_overrides[get_measurement_service] = lambda: service
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
            "cache": {"status": "miss", "last_updated": None, "stale": False},
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

    def test_the_source_is_asked_for_whole_months_in_utc(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        # 00:30 on 1 August in Madrid is still 31 July in UTC, so July is needed too.
        get_ok(api, start="2026-08-01T00:30:00", end="2026-08-01T06:00:00")

        assert source.calls == [
            ("89064", utc("2026-07-01T00:00:00"), utc("2026-07-31T23:59:59")),
            ("89064", utc("2026-08-01T00:00:00"), utc("2026-08-31T23:59:59")),
        ]

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


class TestLetterCase:
    """``aggregation``, ``metrics`` and ``format`` accept any letter case, like ``types``."""

    def test_values_in_any_case_are_accepted_and_answered_in_lower_case(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 6)

        body = get_ok(
            api,
            start="2026-01-15T03:00:00Z",
            end="2026-01-15T03:50:00Z",
            aggregation="Hourly",
            metrics="EXTENDED",
            types="Speed",
        )

        assert body["metadata"]["aggregation"] == "hourly"
        assert "speed_cubic_mean_ms" in body["data"][0]

    def test_format_in_upper_case_returns_csv(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 6)

        response = api.get(
            URL,
            params={
                "start": "2026-01-15T03:00:00Z",
                "end": "2026-01-15T03:50:00Z",
                "format": "CSV",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"


class TestEmptyResults:
    def test_empty_aemet_result_explains_the_seasonal_campaigns(
        self, settings: Settings, source: FakeWeatherSource, make_service: ServiceFactory
    ) -> None:
        app = create_app(settings)
        service = make_service(source, "aemet")
        app.dependency_overrides[get_measurement_service] = lambda: service

        with TestClient(app) as client:
            response = client.get(
                URL, params={"start": "2026-10-01T00:00:00", "end": "2026-10-02T00:00:00"}
            )

        assert "austral summer campaigns" in response.json()["metadata"]["notice"]

    def test_empty_demo_result_without_any_recording(self, api: TestClient) -> None:
        body = get_ok(api, start="2026-10-01T00:00:00", end="2026-10-02T00:00:00")

        assert (
            body["metadata"]["notice"] == "Demo mode: there is no recorded data for Juan Carlos I."
        )


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


class TestWindMetrics:
    """``metrics=extended`` (constant 1 °C, 980 hPa and 5 m/s from ``grid``)."""

    def test_extended_metrics_are_added_to_aggregated_rows(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 144)

        body = get_ok(
            api,
            start="2026-01-15T03:00:00Z",
            end="2026-01-16T02:50:00Z",
            aggregation="daily",
            metrics="extended",
        )

        [row] = body["data"]
        # rho = 98,000 Pa / (287.05 x 274.15 K) = 1.2453 kg/m³; ½ x rho x 5³ = 77.83 W/m².
        assert {key: row[key] for key in list(row)[6:12]} == {
            "speed_cubic_mean_ms": 5.0,
            "speed_max_ms": 5.0,
            "temperature_min_c": 1.0,
            "temperature_max_c": 1.0,
            "air_density_kgm3": 1.245,
            "power_density_wm2": 77.8,
        }
        assert list(body["fields"])[6:12] == [
            "speed_cubic_mean_ms",
            "speed_max_ms",
            "temperature_min_c",
            "temperature_max_c",
            "air_density_kgm3",
            "power_density_wm2",
        ]
        assert body["fields"]["power_density_wm2"] == {
            "label": "Wind power density (W/m²)",
            "unit": "W/m²",
        }
        assert row["samples"] == 144

    def test_only_metrics_whose_inputs_are_requested_appear(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 6)

        body = get_ok(
            api,
            start="2026-01-15T03:00:00Z",
            end="2026-01-15T03:50:00Z",
            aggregation="hourly",
            types="speed",
            metrics="extended",
        )

        assert list(body["data"][0]) == [
            "station",
            "datetime",
            "speed_ms",
            "speed_cubic_mean_ms",
            "speed_max_ms",
            "samples",
            "expected_samples",
            "coverage",
        ]

    def test_without_the_parameter_the_rows_are_unchanged(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 6)

        body = get_ok(
            api, start="2026-01-15T03:00:00Z", end="2026-01-15T03:50:00Z", aggregation="hourly"
        )

        assert "power_density_wm2" not in body["data"][0]
        assert "power_density_wm2" not in body["fields"]

    def test_csv_carries_the_metric_labels(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 6)

        response = api.get(
            URL,
            params={
                "start": "2026-01-15T03:00:00Z",
                "end": "2026-01-15T03:50:00Z",
                "aggregation": "hourly",
                "metrics": "extended",
                "format": "csv",
            },
        )

        header = response.content.decode("utf-8-sig").splitlines()[0]
        assert header == (
            "Station,Datetime,Temperature (°C),Pressure (hPa),Speed (m/s),"
            "Cubic mean speed (m/s),Maximum 10-minute speed (m/s),"
            "Minimum 10-minute temperature (°C),Maximum 10-minute temperature (°C),"
            "Air density (kg/m³),Wind power density (W/m²),Samples,Expected samples,Coverage (%)"
        )


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
            (
                {
                    "start": "2026-01-15T00:00:00",
                    "end": "2026-01-16T00:00:00",
                    "metrics": "extended",
                },
                "metrics",
                "choose an aggregation level",
            ),
            (
                {
                    "start": "2026-01-15T00:00:00",
                    "end": "2026-01-16T00:00:00",
                    "aggregation": "daily",
                    "metrics": "basic",
                },
                "metrics",
                "Input should be",
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
        self, settings: Settings, source: FakeWeatherSource, make_service: ServiceFactory
    ) -> None:
        source.error = RuntimeError("database password is hunter2")
        app = create_app(settings)
        service = make_service(source, "demo")
        app.dependency_overrides[get_measurement_service] = lambda: service

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get(
                URL, params={"start": "2026-01-15T00:00:00", "end": "2026-01-16T00:00:00"}
            )

        assert response.status_code == 500
        assert response.json()["error"]["code"] == "internal_error"
        assert "hunter2" not in response.text


class TestCsvExport:
    def test_daily_csv_uses_the_official_labels(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T03:00:00", 144)

        response = api.get(
            URL,
            params={
                "start": "2026-01-15T03:00:00Z",
                "end": "2026-01-16T02:50:00Z",
                "aggregation": "daily",
                "format": "csv",
            },
        )

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/csv; charset=utf-8"
        assert response.headers["content-disposition"] == (
            'attachment; filename="juan-carlos-i_daily_2026-01-15_2026-01-16.csv"'
        )
        assert response.content.startswith(b"\xef\xbb\xbf")  # BOM, for Excel
        lines = response.content.decode("utf-8-sig").splitlines()
        assert lines == [
            "Station,Datetime,Period,Temperature (°C),Pressure (hPa),Speed (m/s),"
            "Samples,Expected samples,Coverage (%)",
            "Juan Carlos I,2026-01-15T04:00:00+01:00,2026-01-15,1.0,980.0,5.0,144,144,100.0",
        ]

    def test_raw_csv_with_selected_types_and_missing_values(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T00:00:00", 1, temperature=None)

        response = api.get(
            URL,
            params={
                "start": "2026-01-15T00:00:00Z",
                "end": "2026-01-15T00:10:00Z",
                "types": "temperature,speed",
                "format": "csv",
            },
        )

        assert response.content.decode("utf-8-sig").splitlines() == [
            "Station,Datetime,Temperature (°C),Speed (m/s)",
            "Juan Carlos I,2026-01-15T01:00:00+01:00,,5.0",
        ]

    def test_unknown_format_is_rejected(self, api: TestClient) -> None:
        response = api.get(
            URL,
            params={"start": "2026-01-15T00:00:00", "end": "2026-01-16T00:00:00", "format": "xml"},
        )

        assert response.status_code == 422
        assert response.json()["error"]["parameter"] == "format"


class TestCacheMetadata:
    def test_a_repeated_request_is_served_from_the_cache_and_says_so(
        self, api: TestClient, source: FakeWeatherSource
    ) -> None:
        source.observations = grid("2026-01-15T00:00:00", 3)
        params = {"start": "2026-01-15T00:00:00Z", "end": "2026-01-15T00:20:00Z"}

        first = api.get(URL, params=params)
        second = api.get(URL, params=params)

        assert first.headers["X-Cache-Status"] == "miss"
        assert second.headers["X-Cache-Status"] == "hit"
        assert second.headers["X-Data-Stale"] == "false"
        assert second.json()["metadata"]["cache"] == {
            "status": "hit",
            "last_updated": None,
            "stale": False,
        }
        assert second.json()["data"] == first.json()["data"]
        assert len(source.calls) == 1

    def test_last_updated_is_given_for_a_month_that_can_still_change(self, api: TestClient) -> None:
        body = get_ok(api, start="2026-11-10T00:00:00Z", end="2026-11-11T00:00:00Z")

        assert body["metadata"]["cache"] == {
            "status": "miss",
            "last_updated": "2026-11-15T13:00:00+01:00",  # NOW in Madrid time
            "stale": False,
        }

    def test_csv_downloads_carry_the_cache_status_header(self, api: TestClient) -> None:
        params = {"start": "2026-01-15T00:00:00Z", "end": "2026-01-15T00:20:00Z", "format": "csv"}

        assert api.get(URL, params=params).headers["X-Cache-Status"] == "miss"
        assert api.get(URL, params=params).headers["X-Cache-Status"] == "hit"


NOVEMBER_10 = {"start": "2026-11-10T00:00:00Z", "end": "2026-11-11T00:00:00Z"}


class TestStaleData:
    def test_an_expired_month_is_served_stale_when_aemet_fails(
        self, api: TestClient, source: FakeWeatherSource, clock: FakeClock
    ) -> None:
        source.observations = grid("2026-11-10T00:00:00", 3)
        get_ok(api, **NOVEMBER_10)
        clock.now = NOW + timedelta(hours=2)  # November has expired
        source.error = UpstreamUnavailableError("AEMET could not be reached.")

        response = api.get(URL, params=NOVEMBER_10)
        csv = api.get(URL, params={**NOVEMBER_10, "format": "csv"})

        assert response.status_code == 200
        assert response.json()["metadata"]["cache"] == {
            "status": "hit",
            "last_updated": "2026-11-15T13:00:00+01:00",  # the copy being served
            "stale": True,
        }
        assert response.json()["metadata"]["count"] == 3
        assert (response.headers["X-Cache-Status"], response.headers["X-Data-Stale"]) == (
            "hit",
            "true",
        )
        assert csv.headers["X-Data-Stale"] == "true"

    def test_a_month_without_a_copy_fails_fast_while_aemet_is_cooling_down(
        self, api: TestClient, source: FakeWeatherSource, clock: FakeClock
    ) -> None:
        get_ok(api, **NOVEMBER_10)
        clock.now = NOW + timedelta(hours=2)
        source.error = UpstreamUnavailableError("AEMET could not be reached.")
        api.get(URL, params=NOVEMBER_10)  # the failed refresh opens the circuit
        calls_so_far = len(source.calls)
        clock.now += timedelta(seconds=15)

        response = api.get(
            URL, params={"start": "2026-09-10T00:00:00Z", "end": "2026-09-11T00:00:00Z"}
        )

        assert response.status_code == 503
        assert response.headers["Retry-After"] == "45"
        assert response.json()["error"]["code"] == "upstream_unavailable"
        assert "Try again in 45 seconds" in response.json()["error"]["message"]
        assert len(source.calls) == calls_so_far  # AEMET was not called
