"""Tests for the AEMET client with a mocked HTTP layer: no request ever reaches the real AEMET."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr
from tenacity import wait_none

from app.clients.aemet import AemetAntarcticaClient
from app.core.exceptions import UpstreamError, UpstreamTimeoutError, UpstreamUnavailableError
from app.domain.stations import get_station

BASE_URL = "https://aemet.test/opendata"
DATA_URL = "https://aemet.test/opendata/sh/data"
LATIN_TEXT = {"content-type": "text/plain;charset=ISO-8859-15"}
FIXTURES = Path(__file__).parents[1] / "fixtures" / "aemet"
DAY_OF_DATA = (FIXTURES / "data_89064_2026-01-15_2026-01-16.json").read_bytes()
STATION = get_station("juan-carlos-i")


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def envelope_url(start: str, end: str) -> str:
    return f"{BASE_URL}/api/antartida/datos/fechaini/{start}UTC/fechafin/{end}UTC/estacion/89064"


def envelope(estado: int, descripcion: str = "exito") -> httpx.Response:
    body: dict[str, object] = {"descripcion": descripcion, "estado": estado}
    if estado == 200:
        body["datos"] = DATA_URL
    return httpx.Response(200, content=json.dumps(body).encode(), headers=LATIN_TEXT)


@pytest.fixture
def router() -> Iterator[respx.MockRouter]:
    # assert_all_mocked: any request without a matching route fails instead of reaching the network.
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as mock:
        yield mock


@pytest.fixture(scope="module")
def http() -> Iterator[httpx.Client]:
    # Shared by the module: building an httpx.Client loads the SSL context, which is slow.
    with httpx.Client() as shared_client:
        yield shared_client


@pytest.fixture
def client(http: httpx.Client) -> AemetAntarcticaClient:
    return AemetAntarcticaClient(
        http, api_key=SecretStr("test-key"), base_url=BASE_URL, max_attempts=3, wait=wait_none()
    )


DAY_ENVELOPE = envelope_url("2026-01-15T00:00:00", "2026-01-16T00:00:00")


class TestTwoStepProtocol:
    def test_envelope_then_data(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        envelope_route = router.get(DAY_ENVELOPE).mock(return_value=envelope(200))
        data_route = router.get(DATA_URL).respond(200, content=DAY_OF_DATA, headers=LATIN_TEXT)

        observations = client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))

        assert len(observations) == 145
        assert envelope_route.calls.last.request.headers["api_key"] == "test-key"
        assert "api_key" not in data_route.calls.last.request.headers

    def test_no_data_is_an_empty_result(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        router.get(DAY_ENVELOPE).mock(return_value=envelope(404, "No hay datos"))
        data_route = router.get(DATA_URL)

        assert client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00")) == []
        assert not data_route.called

    def test_results_are_limited_to_the_requested_range(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        router.get(envelope_url("2026-01-15T06:00:00", "2026-01-15T07:00:00")).mock(
            return_value=envelope(200)
        )
        router.get(DATA_URL).respond(200, content=DAY_OF_DATA, headers=LATIN_TEXT)

        observations = client.fetch(STATION, utc("2026-01-15T06:00:00"), utc("2026-01-15T07:00:00"))

        assert [o.timestamp.strftime("%H:%M") for o in observations] == [
            "06:00", "06:10", "06:20", "06:30", "06:40", "06:50", "07:00",
        ]  # fmt: skip

    def test_ranges_are_split_into_calendar_months(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        january = router.get(envelope_url("2026-01-31T12:00:00", "2026-01-31T23:59:59")).mock(
            return_value=envelope(404)
        )
        february = router.get(envelope_url("2026-02-01T00:00:00", "2026-02-01T12:00:00")).mock(
            return_value=envelope(404)
        )

        client.fetch(STATION, utc("2026-01-31T12:00:00"), utc("2026-02-01T12:00:00"))

        assert january.call_count == 1
        assert february.call_count == 1


class TestRetries:
    def test_rate_limit_is_retried(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        route = router.get(DAY_ENVELOPE).mock(side_effect=[httpx.Response(429), envelope(404)])

        assert client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00")) == []
        assert route.call_count == 2

    def test_rate_limit_reported_in_the_body_is_retried(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        route = router.get(DAY_ENVELOPE).mock(side_effect=[envelope(429), envelope(404)])

        client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))

        assert route.call_count == 2

    def test_persistent_rate_limit_means_unavailable(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        route = router.get(DAY_ENVELOPE).respond(429)

        with pytest.raises(UpstreamUnavailableError, match="rate limiting"):
            client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))
        assert route.call_count == 3

    def test_persistent_server_error_is_an_upstream_error(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        router.get(DAY_ENVELOPE).respond(503)

        with pytest.raises(UpstreamError, match="HTTP 503") as excinfo:
            client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))
        assert excinfo.type is UpstreamError

    def test_timeouts_are_retried_then_reported(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        route = router.get(DAY_ENVELOPE).mock(side_effect=httpx.ReadTimeout("slow"))

        with pytest.raises(UpstreamTimeoutError):
            client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))
        assert route.call_count == 3

    def test_unreachable_host_means_unavailable(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        router.get(DAY_ENVELOPE).mock(side_effect=httpx.ConnectError("no route"))

        with pytest.raises(UpstreamUnavailableError, match="could not be reached"):
            client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))


class TestPermanentErrors:
    def test_rejected_api_key_is_not_retried_and_never_echoed(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        route = router.get(DAY_ENVELOPE).respond(401)

        with pytest.raises(UpstreamError, match="rejected the API key") as excinfo:
            client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))
        assert route.call_count == 1
        assert "test-key" not in str(excinfo.value)

    def test_error_reported_in_the_envelope(
        self, router: respx.MockRouter, client: AemetAntarcticaClient
    ) -> None:
        router.get(DAY_ENVELOPE).mock(
            return_value=envelope(400, "El rango de fechas no puede ser superior a 1 mes")
        )

        with pytest.raises(UpstreamError, match="estado 400"):
            client.fetch(STATION, utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))
