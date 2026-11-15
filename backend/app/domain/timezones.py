"""Time zone rules: how local times are interpreted and how output datetimes are written.

All internal computation uses timezone-aware datetimes in UTC. Local times only appear at the
edges of the system: when parsing the client's input and when formatting the response.
"""

import re
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from functools import cache
from typing import Final
from zoneinfo import ZoneInfo, available_timezones

from app.core.exceptions import (
    AmbiguousLocalTimeError,
    InvalidParameterError,
    NonExistentLocalTimeError,
)

MADRID: Final = ZoneInfo("Europe/Madrid")
OUTPUT_TIMEZONE: Final = MADRID
"""Output datetimes are always expressed in Europe/Madrid (CET/CEST) and carry their offset."""
DEFAULT_INPUT_TIMEZONE: Final = MADRID
"""Input datetimes without an offset or a ``tz`` parameter are interpreted in Europe/Madrid."""

_OFFSET_PATTERN: Final = re.compile(r"([+-])(\d{2}):(\d{2})")
# In a query string '+' is decoded as a space, so "+02:00" arrives as " 02:00". A valid offset
# never starts with a space, so this can only mean "+02:00" and is accepted as such.
_SPACE_DECODED_OFFSET: Final = re.compile(r" (\d{2}:\d{2})")
_MAX_OFFSET: Final = timedelta(hours=14)


@cache
def _iana_zone_names() -> frozenset[str]:
    # Checking against the official list keeps lookups case-sensitive on every operating system.
    return frozenset(available_timezones())


def restore_plus_sign(value: str) -> str:
    """Turn an offset whose '+' was URL-decoded as a space back into a '+' offset."""
    return _SPACE_DECODED_OFFSET.sub(r"+\1", value)


def format_offset(offset: timedelta) -> str:
    """Format a UTC offset as ``+HH:MM`` / ``-HH:MM``."""
    sign = "-" if offset < timedelta(0) else "+"
    hours, remainder = divmod(abs(offset), timedelta(hours=1))
    return f"{sign}{hours:02d}:{remainder // timedelta(minutes=1):02d}"


def parse_timezone(value: str) -> tzinfo:
    """Parse the ``tz`` parameter: an IANA zone name (``Europe/Berlin``) or an offset (``+02:00``).

    Raises:
        InvalidParameterError: If the value is neither.
    """
    candidate = restore_plus_sign(value)
    if match := _OFFSET_PATTERN.fullmatch(candidate):
        sign, hours, minutes = match.groups()
        offset = timedelta(hours=int(hours), minutes=int(minutes))
        if int(minutes) < 60 and offset <= _MAX_OFFSET:
            return timezone(-offset if sign == "-" else offset)
    elif candidate in _iana_zone_names():
        return ZoneInfo(candidate)
    raise InvalidParameterError(
        "tz",
        f"'{value}' is neither an IANA time zone name (e.g. Europe/Berlin) "
        "nor a UTC offset between -14:00 and +14:00 (e.g. +02:00).",
    )


def describe_timezone(zone: tzinfo) -> str:
    """Human-readable name of a time zone: its IANA key or its offset."""
    if isinstance(zone, ZoneInfo):
        return zone.key
    offset = zone.utcoffset(None)
    return "UTC" if offset == timedelta(0) else format_offset(offset or timedelta(0))


def localize_strict(local: datetime, zone: tzinfo, *, parameter: str, raw: str) -> datetime:
    """Interpret a naive local time in ``zone`` and return it as an aware UTC datetime.

    Python never raises for problematic local times: it silently picks one interpretation using
    the ``fold`` attribute (0 = first occurrence, 1 = second). This function detects them instead:

    - The two interpretations have the same offset: the time is unique (the normal case).
    - Different offsets, and converting the first one to UTC and back gives a different wall
      time: the time does not exist (the clocks skip it when DST starts).
    - Different offsets otherwise: the time is ambiguous (it occurs twice when DST ends).

    Raises:
        NonExistentLocalTimeError: For times skipped by the spring-forward change.
        AmbiguousLocalTimeError: For times repeated by the fall-back change.
    """
    first = local.replace(tzinfo=zone, fold=0)
    second = local.replace(tzinfo=zone, fold=1)
    first_offset, second_offset = _utc_offset(first), _utc_offset(second)
    if first_offset == second_offset:
        return first.astimezone(UTC)

    zone_name = describe_timezone(zone)
    if first.astimezone(UTC).astimezone(zone).replace(tzinfo=None) != local:
        raise NonExistentLocalTimeError(
            parameter,
            f"'{raw}' does not exist in {zone_name}: the clocks skip this local time when "
            "daylight saving time starts. Use a time outside the skipped interval or an "
            "explicit UTC offset.",
        )
    raise AmbiguousLocalTimeError(
        parameter,
        f"'{raw}' is ambiguous in {zone_name}: it occurs twice when daylight saving time ends. "
        f"Use the offset {format_offset(first_offset)} for the first occurrence or "
        f"{format_offset(second_offset)} for the second (in a URL, write '+' as %2B).",
    )


def format_output_datetime(instant: datetime) -> str:
    """Write an aware datetime in the output time zone with its offset (``...T05:00:00+02:00``)."""
    if instant.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed: the instant would be ambiguous.")
    return instant.astimezone(OUTPUT_TIMEZONE).isoformat(timespec="seconds")


def _utc_offset(value: datetime) -> timedelta:
    offset = value.utcoffset()
    if offset is None:  # cannot happen for a datetime with a tzinfo; keeps the type checker exact
        raise ValueError("Expected a timezone-aware datetime.")
    return offset
