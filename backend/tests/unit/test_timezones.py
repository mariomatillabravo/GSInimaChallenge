"""Unit tests for time zone parsing and formatting helpers."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.core.exceptions import InvalidParameterError
from app.domain.timezones import format_offset, format_output_datetime, parse_timezone


@pytest.mark.parametrize("name", ["Europe/Madrid", "Europe/Berlin", "America/Punta_Arenas", "UTC"])
def test_iana_names_are_accepted(name: str) -> None:
    zone = parse_timezone(name)

    assert isinstance(zone, ZoneInfo)
    assert zone.key == name


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("+02:00", timedelta(hours=2)),
        ("-03:00", timedelta(hours=-3)),
        ("+05:30", timedelta(hours=5, minutes=30)),
        ("+00:00", timedelta(0)),
        (" 02:00", timedelta(hours=2)),  # '+' decoded as a space in a query string
    ],
)
def test_offsets_are_accepted(value: str, expected: timedelta) -> None:
    assert parse_timezone(value).utcoffset(None) == expected


@pytest.mark.parametrize(
    "value",
    ["Mars/Olympus", "europe/madrid", "", "+2", "02:00", "+14:30", "+05:60", "UTC+2"],
)
def test_invalid_time_zones_are_rejected(value: str) -> None:
    with pytest.raises(InvalidParameterError) as excinfo:
        parse_timezone(value)

    assert excinfo.value.parameter == "tz"


def test_format_offset() -> None:
    assert format_offset(timedelta(hours=2)) == "+02:00"
    assert format_offset(timedelta(hours=-3, minutes=-30)) == "-03:30"
    assert format_offset(timedelta(0)) == "+00:00"


def test_naive_datetimes_cannot_be_formatted() -> None:
    with pytest.raises(ValueError, match="Naive datetimes are not allowed"):
        format_output_datetime(datetime.fromisoformat("2026-01-15T00:00:00"))
