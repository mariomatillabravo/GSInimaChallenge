"""Unit tests of the conversion between aware datetimes and the epoch seconds in the cache."""

from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.db.repository import from_epoch_seconds, to_epoch_seconds

JAN_15_2026 = 1_768_435_200
"""Seconds since the epoch at 2026-01-15T00:00:00Z."""


def test_known_instant() -> None:
    assert to_epoch_seconds(datetime(2026, 1, 15, tzinfo=UTC)) == JAN_15_2026
    assert from_epoch_seconds(JAN_15_2026) == datetime(2026, 1, 15, tzinfo=UTC)


def test_the_same_instant_in_any_zone_gives_the_same_number() -> None:
    madrid = datetime(2026, 1, 15, 1, 0, tzinfo=ZoneInfo("Europe/Madrid"))
    station = datetime(2026, 1, 14, 21, 0, tzinfo=timezone(timedelta(hours=-3)))

    assert to_epoch_seconds(madrid) == to_epoch_seconds(station) == JAN_15_2026


def test_results_are_in_utc() -> None:
    assert from_epoch_seconds(JAN_15_2026).utcoffset() == timedelta(0)


def test_fractions_of_a_second_are_rounded_down() -> None:
    moment = datetime(2026, 1, 15, 0, 0, 1, 999_999, tzinfo=UTC)

    assert to_epoch_seconds(moment) == JAN_15_2026 + 1


def test_naive_datetimes_are_rejected() -> None:
    with pytest.raises(ValueError, match="Naive"):
        to_epoch_seconds(datetime(2026, 1, 15))  # noqa: DTZ001 - naive on purpose


# Hypothesis takes naive bounds and attaches the time zone to every generated value.
@given(st.datetimes(min_value=datetime(1970, 1, 1), timezones=st.just(UTC)))  # noqa: DTZ001
def test_round_trip_keeps_whole_seconds(moment: datetime) -> None:
    whole_seconds = moment.replace(microsecond=0)

    assert from_epoch_seconds(to_epoch_seconds(whole_seconds)) == whole_seconds
