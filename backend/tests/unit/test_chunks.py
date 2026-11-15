"""Unit tests for splitting ranges into calendar months in UTC."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from app.domain.chunks import month_chunks


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def test_range_inside_one_month_gives_the_whole_month() -> None:
    [chunk] = month_chunks(utc("2026-01-15T00:00:00"), utc("2026-01-16T00:00:00"))

    assert chunk.key == "2026-01"
    assert chunk.start == utc("2026-01-01T00:00:00")
    assert chunk.end == utc("2026-01-31T23:59:59")


def test_range_across_a_year_boundary() -> None:
    chunks = month_chunks(utc("2025-12-31T12:00:00"), utc("2026-02-10T00:00:00"))

    assert [chunk.key for chunk in chunks] == ["2025-12", "2026-01", "2026-02"]
    assert chunks[1].end == utc("2026-01-31T23:59:59")
    assert chunks[2].start == utc("2026-02-01T00:00:00")


def test_inclusive_end_on_the_first_instant_of_a_month_includes_that_month() -> None:
    chunks = month_chunks(utc("2026-01-15T00:00:00"), utc("2026-02-01T00:00:00"))

    assert [chunk.key for chunk in chunks] == ["2026-01", "2026-02"]


def test_months_are_computed_in_utc() -> None:
    madrid = ZoneInfo("Europe/Madrid")
    start = datetime(2026, 2, 1, 0, 30, tzinfo=madrid)  # 2026-01-31T23:30Z

    assert [chunk.key for chunk in month_chunks(start, start)] == ["2026-01"]


def test_leap_february() -> None:
    [chunk] = month_chunks(utc("2028-02-10T00:00:00"), utc("2028-02-11T00:00:00"))

    assert chunk.end == utc("2028-02-29T23:59:59")


def test_naive_datetimes_are_rejected() -> None:
    naive = datetime.fromisoformat("2026-01-15T00:00:00")

    with pytest.raises(ValueError, match="Naive"):
        month_chunks(naive, naive)
