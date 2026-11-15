"""Resolution and validation of the time range requested by the client."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Final

from app.core.exceptions import InvalidParameterError, RangeTooLargeError
from app.domain.measurements import Aggregation
from app.domain.timezones import (
    DEFAULT_INPUT_TIMEZONE,
    describe_timezone,
    localize_strict,
    parse_timezone,
    restore_plus_sign,
)

_DATETIME_PATTERN: Final = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})?")
_EXPECTED_FORMAT: Final = (
    "Expected YYYY-MM-DDTHH:MM:SS, optionally followed by Z or a UTC offset such as +02:00."
)


@dataclass(frozen=True, slots=True)
class TimeRange:
    """A validated time range. Both ends are aware UTC datetimes and both are inclusive."""

    start: datetime
    end: datetime
    input_interpretation: str
    """How the client's datetimes were interpreted, e.g. ``"Europe/Madrid (default)"``."""


def resolve_range(start: str, end: str, tz: str | None) -> TimeRange:
    """Interpret the ``start``, ``end`` and ``tz`` parameters as an inclusive UTC range.

    Rules:
        - A datetime may carry its own offset (``+02:00`` or ``Z``).
        - Datetimes without an offset are interpreted in ``tz`` or, when it is absent, in
          Europe/Madrid. Non-existent and ambiguous local times are rejected.
        - Giving ``tz`` together with a datetime that has its own offset is a conflict.

    Raises:
        InvalidParameterError: For malformed values, conflicts or an empty range.
    """
    zone = parse_timezone(tz) if tz is not None else None
    start_value, end_value = _parse_datetime(start, "start"), _parse_datetime(end, "end")
    if zone is not None and (start_value.tzinfo is not None or end_value.tzinfo is not None):
        raise InvalidParameterError(
            "tz", "Specify the UTC offset either in the datetimes or in tz, not both."
        )

    start_utc, start_description = _to_utc(start_value, zone, parameter="start", raw=start)
    end_utc, end_description = _to_utc(end_value, zone, parameter="end", raw=end)
    if end_utc <= start_utc:
        raise InvalidParameterError("end", "end must be later than start.")

    interpretation = (
        start_description
        if start_description == end_description
        else f"start: {start_description}; end: {end_description}"
    )
    return TimeRange(start=start_utc, end=end_utc, input_interpretation=interpretation)


def validate_range_length(
    time_range: TimeRange, aggregation: Aggregation, max_days: int | None
) -> None:
    """Reject ranges longer than the maximum allowed for the aggregation level.

    Raises:
        RangeTooLargeError: If the range is longer than ``max_days`` (``None`` means no limit).
    """
    if max_days is None or time_range.end - time_range.start <= timedelta(days=max_days):
        return
    levels = list(Aggregation)
    coarser = levels[levels.index(aggregation) + 1 :]
    advice = f" or use a coarser aggregation ({', '.join(level.value for level in coarser)})"
    raise RangeTooLargeError(
        "end",
        f"The range is longer than {max_days} days, the maximum for "
        f"aggregation={aggregation.value}. Reduce the range{advice if coarser else ''}.",
    )


def _parse_datetime(raw: str, parameter: str) -> datetime:
    value = restore_plus_sign(raw)
    if not _DATETIME_PATTERN.fullmatch(value):
        raise InvalidParameterError(
            parameter, f"'{raw}' is not a valid datetime. {_EXPECTED_FORMAT}"
        )
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise InvalidParameterError(
            parameter, f"'{raw}' is not a valid calendar date or time. {_EXPECTED_FORMAT}"
        ) from None


def _to_utc(
    value: datetime, zone: tzinfo | None, *, parameter: str, raw: str
) -> tuple[datetime, str]:
    """Convert a parsed datetime to UTC and describe how it was interpreted."""
    if value.tzinfo is not None:
        description = f"{describe_timezone(value.tzinfo)} (embedded in the datetime)"
        return value.astimezone(UTC), description
    if zone is not None:
        utc = localize_strict(value, zone, parameter=parameter, raw=raw)
        return utc, f"{describe_timezone(zone)} (tz parameter)"
    utc = localize_strict(value, DEFAULT_INPUT_TIMEZONE, parameter=parameter, raw=raw)
    return utc, f"{describe_timezone(DEFAULT_INPUT_TIMEZONE)} (default)"
