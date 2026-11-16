"""Client for the AEMET OpenData Antarctica endpoint."""

import logging
from datetime import UTC, datetime
from typing import Any, Final

import httpx
from pydantic import SecretStr
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential
from tenacity.wait import wait_base

from app.clients.aemet_parser import (
    decode_body,
    load_records,
    parse_envelope,
    parse_observations,
)
from app.clients.cleaning_log import log_discarded
from app.core.exceptions import UpstreamError, UpstreamTimeoutError, UpstreamUnavailableError
from app.domain.chunks import month_chunks
from app.domain.measurements import Observation
from app.domain.stations import Station

DEFAULT_BASE_URL: Final = "https://opendata.aemet.es/opendata"
_ENDPOINT: Final = "/api/antartida/datos/fechaini/{start}/fechafin/{end}/estacion/{station}"
_URL_DATE_FORMAT: Final = "%Y-%m-%dT%H:%M:%SUTC"
_ESTADO_OK: Final = 200
_ESTADO_NO_DATA: Final = 404
_ESTADO_RATE_LIMITED: Final = 429

logger = logging.getLogger(__name__)


class _RateLimitedError(Exception):
    """AEMET asked us to slow down. Retried; reported as 'unavailable' if it persists."""


class _ServerError(Exception):
    """AEMET failed with a 5xx status. Retried; reported as an upstream error if it persists."""


class AemetAntarcticaClient:
    """``WeatherSource`` backed by the AEMET OpenData Antarctica endpoint.

    - Splits the requested range into calendar months, the longest range AEMET accepts.
    - Follows the two-step protocol: an envelope first, then the data it points to.
    - Reads the outcome from the envelope's ``estado``: the HTTP status is 200 even for errors.
    - Retries transient failures (network errors, timeouts, rate limiting, 5xx) with
      exponential backoff. Permanent failures, such as a rejected API key, are not retried.
    """

    def __init__(
        self,
        http: httpx.Client,
        *,
        api_key: SecretStr,
        base_url: str = DEFAULT_BASE_URL,
        max_attempts: int = 3,
        wait: wait_base | None = None,
    ) -> None:
        """Create the client.

        Args:
            http: Shared HTTP client; its lifecycle (and timeout) is managed by the application.
            api_key: AEMET API key, sent only in the ``api_key`` header of the first request.
            base_url: AEMET OpenData base URL.
            max_attempts: Attempts per monthly window, including the first one.
            wait: Pause between attempts. Exponential backoff by default; tests pass no wait.
        """
        self._http = http
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._retrying = Retrying(
            retry=retry_if_exception_type((httpx.TransportError, _RateLimitedError, _ServerError)),
            stop=stop_after_attempt(max_attempts),
            wait=wait if wait is not None else wait_exponential(multiplier=0.5, max=8),
            reraise=True,
        )

    def fetch(self, station: Station, start: datetime, end: datetime) -> list[Observation]:
        """Return the cleaned observations of ``station`` in ``[start, end]``, sorted by time."""
        observations: list[Observation] = []
        # Windows are disjoint and visited in order, so concatenating keeps the result sorted.
        for window_start, window_end in _monthly_windows(start, end):
            text = self._fetch_window(station, window_start, window_end)
            if text is not None:
                parsed = parse_observations(text)
                log_discarded(logger, parsed, station, month=window_start.strftime("%Y-%m"))
                observations.extend(
                    obs
                    for obs in parsed.observations
                    if window_start <= obs.timestamp <= window_end
                )
        return observations

    def fetch_raw_records(
        self, station: Station, start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        """Return the records exactly as AEMET serves them, without any cleaning.

        Used by the script that records demo data, so that recordings go through the same
        protocol, retries and error handling as live requests.
        """
        records: list[dict[str, Any]] = []
        for window_start, window_end in _monthly_windows(start, end):
            text = self._fetch_window(station, window_start, window_end)
            if text is not None:
                records.extend(load_records(text))
        return records

    def _fetch_window(self, station: Station, start: datetime, end: datetime) -> str | None:
        """Body of the data response for one window, or ``None`` when AEMET has no data."""
        try:
            return self._retrying.copy()(self._fetch_window_once, station, start, end)
        except httpx.TimeoutException as error:
            raise UpstreamTimeoutError("AEMET did not answer in time.") from error
        except httpx.TransportError as error:
            raise UpstreamUnavailableError("AEMET could not be reached.") from error
        except _RateLimitedError as error:
            raise UpstreamUnavailableError(
                "AEMET is rate limiting requests. Try again later."
            ) from error
        except _ServerError as error:
            raise UpstreamError(f"AEMET failed with {error}.") from error

    def _fetch_window_once(self, station: Station, start: datetime, end: datetime) -> str | None:
        url = self._base_url + _ENDPOINT.format(
            start=_url_date(start), end=_url_date(end), station=station.aemet_id
        )
        headers = {"api_key": self._api_key.get_secret_value()}
        envelope = parse_envelope(self._get_text(url, headers=headers))
        if envelope.status == _ESTADO_NO_DATA:
            return None
        if envelope.status == _ESTADO_RATE_LIMITED:
            raise _RateLimitedError
        if envelope.status != _ESTADO_OK or envelope.data_url is None:
            raise UpstreamError(f"AEMET answered estado {envelope.status}: {envelope.description}")
        return self._get_text(envelope.data_url)

    def _get_text(self, url: str, headers: dict[str, str] | None = None) -> str:
        response = self._http.get(url, headers=headers)
        status = response.status_code
        if status == httpx.codes.TOO_MANY_REQUESTS:
            raise _RateLimitedError
        if status >= httpx.codes.INTERNAL_SERVER_ERROR:
            raise _ServerError(f"HTTP {status}")
        if status in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise UpstreamError("AEMET rejected the API key. Check AEMET_API_KEY.")
        if status != httpx.codes.OK:
            raise UpstreamError(f"Unexpected HTTP {status} from AEMET.")
        return decode_body(response.content, response.charset_encoding)


def _monthly_windows(start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
    """Split ``[start, end]`` into windows that never cross a calendar month (AEMET's limit)."""
    return [(max(chunk.start, start), min(chunk.end, end)) for chunk in month_chunks(start, end)]


def _url_date(instant: datetime) -> str:
    return instant.astimezone(UTC).strftime(_URL_DATE_FORMAT)
