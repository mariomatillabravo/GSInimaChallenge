"""Unit tests for the recorded weather source used in demo mode."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.clients.recorded import RecordedWeatherSource
from app.domain.measurements import Observation
from app.domain.stations import Station, get_station

FIXTURES = Path(__file__).parents[1] / "fixtures" / "aemet"
JUAN_CARLOS_I = get_station("juan-carlos-i")


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def fetch(
    source: RecordedWeatherSource, start: str, end: str, station: Station = JUAN_CARLOS_I
) -> list[Observation]:
    return source.fetch(station, utc(start), utc(end))


@pytest.fixture
def source(tmp_path: Path) -> RecordedWeatherSource:
    # A recording of January 2026 for Juan Carlos I (one real day is enough for these tests).
    shutil.copy(FIXTURES / "data_89064_2026-01-15_2026-01-16.json", tmp_path / "89064_2026-01.json")
    return RecordedWeatherSource(tmp_path)


def test_recorded_month_is_replayed_through_the_real_parser(source: RecordedWeatherSource) -> None:
    observations = fetch(source, "2026-01-15T00:00:00", "2026-01-16T00:00:00")
    partial = next(o for o in observations if o.timestamp == utc("2026-01-15T16:00:00"))

    assert len(observations) == 145
    assert (partial.temperature, partial.speed) == (None, 2.5)  # "NaN" handled by the parser


def test_results_are_limited_to_the_requested_range(source: RecordedWeatherSource) -> None:
    observations = fetch(source, "2026-01-15T06:00:00", "2026-01-15T07:00:00")

    assert len(observations) == 7  # 06:00 to 07:00, both ends included


def test_months_without_a_recording_are_empty(source: RecordedWeatherSource) -> None:
    gabriel = get_station("gabriel-de-castilla")

    assert fetch(source, "2026-01-15T00:00:00", "2026-01-16T00:00:00", station=gabriel) == []
    assert fetch(source, "2026-02-01T00:00:00", "2026-02-02T00:00:00") == []


def test_available_range_spans_every_recorded_month(
    source: RecordedWeatherSource, tmp_path: Path
) -> None:
    shutil.copy(FIXTURES / "data_89064_2023-03-25_2023-03-27.json", tmp_path / "89064_2023-03.json")

    available = source.available_range(JUAN_CARLOS_I)

    assert available is not None
    assert (available.start, available.end) == (
        utc("2023-03-25T00:00:00"),
        utc("2026-01-16T00:00:00"),
    )


def test_station_without_recordings_has_no_available_range(source: RecordedWeatherSource) -> None:
    assert source.available_range(get_station("gabriel-de-castilla")) is None


def test_range_across_months_combines_the_available_recordings(
    source: RecordedWeatherSource,
) -> None:
    observations = fetch(source, "2026-01-15T23:00:00", "2026-02-15T00:00:00")

    assert observations[0].timestamp == utc("2026-01-15T23:00:00")
    assert observations[-1].timestamp == utc("2026-01-16T00:00:00")
