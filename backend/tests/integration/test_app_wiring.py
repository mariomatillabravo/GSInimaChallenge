"""End-to-end tests of the composition root: real wiring, no fakes injected.

Demo mode replays recorded files; real mode calls AEMET through the real client, with the HTTP
layer mocked by respx so that no request leaves the machine.
"""

import json
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

FIXTURES = Path(__file__).parents[1] / "fixtures" / "aemet"
DAY = (FIXTURES / "data_89064_2026-01-15_2026-01-16.json").read_bytes()
URL = "/api/v1/stations/juan-carlos-i/measurements"
PARAMS = {"start": "2026-01-15T03:00:00Z", "end": "2026-01-16T00:00:00Z", "aggregation": "daily"}
# The station day of 2026-01-15 runs from 03:00Z to 02:50Z the next day, and the end of the range
# is inclusive: 03:00Z to 00:00Z is 21 hours x 6 observations + 1 = 127 samples in one daily row.
EXPECTED_SAMPLES = [127]


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        yield mock


def test_demo_mode_serves_recorded_files(tmp_path: Path) -> None:
    shutil.copy(FIXTURES / "data_89064_2026-01-15_2026-01-16.json", tmp_path / "89064_2026-01.json")
    settings = Settings(_env_file=None, demo_mode=True, demo_data_dir=tmp_path)

    with TestClient(create_app(settings)) as client:
        body = client.get(URL, params=PARAMS).json()

    assert body["metadata"]["source"] == "demo"
    assert [row["samples"] for row in body["data"]] == EXPECTED_SAMPLES


def test_real_mode_calls_aemet_through_the_real_client(router: respx.MockRouter) -> None:
    base_url = "https://aemet.test/opendata"
    envelope = {"descripcion": "exito", "estado": 200, "datos": f"{base_url}/sh/day"}
    router.get(url__startswith=f"{base_url}/api/antartida/").respond(
        200, content=json.dumps(envelope)
    )
    router.get(f"{base_url}/sh/day").respond(
        200, content=DAY, headers={"content-type": "text/plain;charset=ISO-8859-15"}
    )
    settings = Settings(_env_file=None, aemet_api_key="test-key", aemet_base_url=base_url)

    with TestClient(create_app(settings)) as client:
        body = client.get(URL, params=PARAMS).json()

    assert body["metadata"]["source"] == "aemet"
    assert [row["samples"] for row in body["data"]] == EXPECTED_SAMPLES
