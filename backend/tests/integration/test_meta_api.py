"""Integration tests for the metadata endpoint used by clients to build their query forms."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

URL = "/api/v1/meta"


def build_client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def real_client() -> Iterator[TestClient]:
    """Real mode: the AEMET client is built at startup but never called by this endpoint."""
    yield from build_client(Settings(_env_file=None, demo_mode=False, aemet_api_key="test-key"))


@pytest.fixture
def custom_limits_client() -> Iterator[TestClient]:
    settings = Settings(
        _env_file=None, demo_mode=True, max_range_days_none=7, max_range_days_monthly=1200
    )
    yield from build_client(settings)


def test_demo_deployment_describes_its_options(client: TestClient) -> None:
    response = client.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "source": "demo",
        "output_timezone": "Europe/Madrid",
        "default_input_timezone": "Europe/Madrid",
        "aggregations": [
            {"id": "none", "max_range_days": 31},
            {"id": "hourly", "max_range_days": 366},
            {"id": "daily", "max_range_days": 3660},
            {"id": "monthly", "max_range_days": None},
        ],
        "measurement_types": [
            {
                "id": "temperature",
                "key": "temperature_c",
                "label": "Temperature (°C)",
                "unit": "°C",
            },
            {"id": "pressure", "key": "pressure_hpa", "label": "Pressure (hPa)", "unit": "hPa"},
            {"id": "speed", "key": "speed_ms", "label": "Speed (m/s)", "unit": "m/s"},
        ],
        "wind_metrics": [
            {
                "id": "speed_cubic_mean",
                "key": "speed_cubic_mean_ms",
                "label": "Cubic mean speed (m/s)",
                "unit": "m/s",
                "inputs": ["speed"],
            },
            {
                "id": "speed_max",
                "key": "speed_max_ms",
                "label": "Maximum 10-minute speed (m/s)",
                "unit": "m/s",
                "inputs": ["speed"],
            },
            {
                "id": "temperature_min",
                "key": "temperature_min_c",
                "label": "Minimum 10-minute temperature (°C)",
                "unit": "°C",
                "inputs": ["temperature"],
            },
            {
                "id": "temperature_max",
                "key": "temperature_max_c",
                "label": "Maximum 10-minute temperature (°C)",
                "unit": "°C",
                "inputs": ["temperature"],
            },
            {
                "id": "air_density",
                "key": "air_density_kgm3",
                "label": "Air density (kg/m³)",
                "unit": "kg/m³",
                "inputs": ["temperature", "pressure"],
            },
            {
                "id": "power_density",
                "key": "power_density_wm2",
                "label": "Wind power density (W/m²)",
                "unit": "W/m²",
                "inputs": ["temperature", "pressure", "speed"],
            },
        ],
    }


def test_real_deployment_reports_aemet_as_its_source(real_client: TestClient) -> None:
    assert real_client.get(URL).json()["source"] == "aemet"


def test_maximum_ranges_follow_the_configuration(custom_limits_client: TestClient) -> None:
    aggregations = custom_limits_client.get(URL).json()["aggregations"]

    limits = {level["id"]: level["max_range_days"] for level in aggregations}
    assert limits == {"none": 7, "hourly": 366, "daily": 3660, "monthly": 1200}


def test_openapi_document_describes_the_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]

    schema_ref = paths[URL]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
    assert schema_ref == {"$ref": "#/components/schemas/MetaResponse"}
