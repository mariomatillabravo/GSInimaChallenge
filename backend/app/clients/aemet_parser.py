"""Pure functions that turn raw AEMET Antarctica responses into domain observations.

They perform no I/O, so contract tests run them directly against real recorded responses. The
upstream behaviour they rely on is documented in ``docs/aemet-api.md``.
"""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from app.core.exceptions import UpstreamError
from app.domain.measurements import MEASUREMENT_FIELDS, MeasurementType, Observation

DEFAULT_CHARSET: Final = "iso-8859-15"
"""Charset declared by AEMET for both envelopes and data."""
BAD_QUALITY_FLAG: Final = 1
"""Value of ``qdato`` for records that AEMET marks as bad quality."""


@dataclass(frozen=True, slots=True)
class Envelope:
    """First step of the two-step response: it points to the actual data."""

    status: int
    """The ``estado`` field. AEMET reports errors here while the HTTP status stays 200."""
    description: str
    data_url: str | None


@dataclass(frozen=True, slots=True)
class ParsedObservations:
    observations: list[Observation]
    """Sorted by time, at most one per timestamp."""
    discarded: int
    """Records dropped because they had no usable value or no valid timestamp."""


def decode_body(content: bytes, charset: str | None) -> str:
    """Decode a response body with the charset declared by the server (ISO-8859-15 by default)."""
    encoding = charset or DEFAULT_CHARSET
    try:
        return content.decode(encoding)
    except (LookupError, UnicodeDecodeError) as error:
        raise UpstreamError(f"AEMET response could not be decoded as {encoding}.") from error


def parse_envelope(text: str) -> Envelope:
    """Parse the first-step response."""
    payload = _load_json(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("estado"), int):
        raise UpstreamError("Unexpected AEMET envelope: the 'estado' field is missing.")
    data_url = payload.get("datos")
    return Envelope(
        status=payload["estado"],
        description=str(payload.get("descripcion", "")),
        data_url=data_url if isinstance(data_url, str) else None,
    )


def parse_observations(text: str) -> ParsedObservations:
    """Parse the second-step response and apply the cleaning rule to every record.

    Cleaning rule:
        - ``"NaN"``, ``null``, a non-numeric value or an absent field: that value is missing.
        - ``qdato == 1`` (bad quality): every value of the record is missing.
        - A record left without any value, or without a valid timestamp, is discarded.

    AEMET does not always sort the records, so they are sorted here. If a timestamp appears
    twice, the last record wins.
    """
    by_timestamp: dict[datetime, Observation] = {}
    discarded = 0
    for record in _load_list(text):
        observation = _parse_record(record) if isinstance(record, dict) else None
        if observation is None:
            discarded += 1
        else:
            by_timestamp[observation.timestamp] = observation
    observations = [by_timestamp[timestamp] for timestamp in sorted(by_timestamp)]
    return ParsedObservations(observations=observations, discarded=discarded)


def load_records(text: str) -> list[dict[str, Any]]:
    """Return the records of a data response exactly as served, without any cleaning."""
    return [record for record in _load_list(text) if isinstance(record, dict)]


def _load_list(text: str) -> list[Any]:
    payload = _load_json(text)
    if not isinstance(payload, list):
        raise UpstreamError("Unexpected AEMET data: expected a list of records.")
    return payload


def _parse_record(record: dict[str, Any]) -> Observation | None:
    timestamp = _parse_timestamp(record.get("fhora"))
    if timestamp is None or _number(record.get("qdato")) == BAD_QUALITY_FLAG:
        return None
    values = {
        kind: _number(record.get(field.aemet_name)) for kind, field in MEASUREMENT_FIELDS.items()
    }
    if all(value is None for value in values.values()):
        return None
    return Observation(
        timestamp=timestamp,
        temperature=values[MeasurementType.TEMPERATURE],
        pressure=values[MeasurementType.PRESSURE],
        speed=values[MeasurementType.SPEED],
    )


def _parse_timestamp(value: object) -> datetime | None:
    """Parse ``fhora`` (ISO-8601 in UTC, e.g. ``2026-01-15T00:10:00Z``)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None  # never guess the time zone of an observation
    return parsed.astimezone(UTC)


def _number(value: object) -> float | None:
    """Return a finite float, or ``None`` for missing values (AEMET writes them as ``"NaN"``)."""
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _load_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise UpstreamError("AEMET returned a response that is not valid JSON.") from error
