"""Unit tests for time aggregation (station local time is UTC-03:00, so days start at 03:00Z)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.aggregation import SeriesRow, build_series
from app.domain.measurements import Aggregation, MeasurementType, Observation
from app.domain.stations import ANTARCTIC_STATION_TIME

ALL_TYPES = list(MeasurementType)
TEMPERATURE, PRESSURE, SPEED = MeasurementType


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def grid(
    start: str,
    count: int,
    temperature: float | None = 1.0,
    pressure: float | None = 980.0,
    speed: float | None = 5.0,
) -> list[Observation]:
    """``count`` observations every ten minutes from ``start`` (UTC)."""
    first = utc(start)
    return [
        Observation(first + timedelta(minutes=10 * step), temperature, pressure, speed)
        for step in range(count)
    ]


def aggregate(
    observations: Sequence[Observation],
    aggregation: Aggregation,
    start: str,
    end: str,
    types: Sequence[MeasurementType] = ALL_TYPES,
) -> list[SeriesRow]:
    return build_series(
        observations,
        aggregation=aggregation,
        types=types,
        station_timezone=ANTARCTIC_STATION_TIME,
        start=utc(start),
        end=utc(end),
    )


class TestRawRows:
    def test_observations_are_returned_with_the_requested_types_only(self) -> None:
        observations = grid("2026-01-15T00:00:00", 3)

        rows = aggregate(
            observations, Aggregation.NONE, "2026-01-15T00:00:00", "2026-01-15T00:20:00", [SPEED]
        )

        assert [row.timestamp for row in rows] == [obs.timestamp for obs in observations]
        assert all(row.values == {SPEED: 5.0} for row in rows)
        assert all(row.samples is None and row.period is None for row in rows)

    def test_observations_without_any_requested_value_are_left_out(self) -> None:
        observations = [
            *grid("2026-01-15T00:00:00", 1),
            *grid("2026-01-15T00:10:00", 1, temperature=None),
        ]

        rows = aggregate(
            observations,
            Aggregation.NONE,
            "2026-01-15T00:00:00",
            "2026-01-15T00:10:00",
            [TEMPERATURE],
        )

        assert len(rows) == 1


class TestMeans:
    def test_hourly_mean(self) -> None:
        observations = [
            Observation(
                utc("2026-01-15T10:00:00") + timedelta(minutes=10 * i), float(i + 1), None, None
            )
            for i in range(6)
        ]

        [row] = aggregate(
            observations,
            Aggregation.HOURLY,
            "2026-01-15T10:00:00",
            "2026-01-15T10:50:00",
            [TEMPERATURE],
        )

        assert row.values == {TEMPERATURE: 3.5}
        assert (row.samples, row.expected_samples, row.coverage) == (6, 6, 100.0)

    def test_missing_values_are_excluded_from_each_mean(self) -> None:
        observations = [
            Observation(utc("2026-01-15T10:00:00"), 1.0, None, 1.0),
            Observation(utc("2026-01-15T10:10:00"), None, None, 2.0),
            Observation(utc("2026-01-15T10:20:00"), 3.0, None, 3.0),
        ]

        [row] = aggregate(
            observations, Aggregation.HOURLY, "2026-01-15T10:00:00", "2026-01-15T10:59:00"
        )

        assert row.values == {TEMPERATURE: 2.0, PRESSURE: None, SPEED: 2.0}
        assert row.samples == 3

    def test_samples_only_count_observations_with_a_requested_value(self) -> None:
        observations = [
            *grid("2026-01-15T10:00:00", 4),
            *grid("2026-01-15T10:40:00", 2, temperature=None),
        ]

        [row] = aggregate(
            observations,
            Aggregation.HOURLY,
            "2026-01-15T10:00:00",
            "2026-01-15T10:59:00",
            [TEMPERATURE],
        )

        assert (row.samples, row.coverage) == (4, 66.7)


class TestCoverage:
    def test_complete_station_day(self) -> None:
        observations = grid("2026-01-15T03:00:00", 144)

        [row] = aggregate(
            observations, Aggregation.DAILY, "2026-01-15T03:00:00", "2026-01-16T02:50:00"
        )

        assert (row.period, row.samples, row.expected_samples, row.coverage) == (
            "2026-01-15",
            144,
            144,
            100.0,
        )

    def test_first_bucket_cut_by_the_requested_range(self) -> None:
        # Starting at 15:00 station time (18:00Z): 54 of the 144 slots of that day.
        observations = grid("2026-01-15T18:00:00", 54)

        [row] = aggregate(
            observations, Aggregation.DAILY, "2026-01-15T18:00:00", "2026-01-16T02:50:00"
        )

        assert (row.samples, row.coverage) == (54, 37.5)

    def test_gap_inside_a_bucket(self) -> None:
        day = grid("2026-01-15T03:00:00", 144)
        observations = day[:60] + day[72:]  # a two-hour outage

        [row] = aggregate(
            observations, Aggregation.DAILY, "2026-01-15T03:00:00", "2026-01-16T02:50:00"
        )

        assert (row.samples, row.coverage) == (132, 91.7)

    def test_empty_buckets_inside_the_range_are_kept(self) -> None:
        observations = [*grid("2026-01-15T03:00:00", 144), *grid("2026-01-17T03:00:00", 144)]

        rows = aggregate(
            observations, Aggregation.DAILY, "2026-01-15T03:00:00", "2026-01-18T02:50:00"
        )

        assert [row.period for row in rows] == ["2026-01-15", "2026-01-16", "2026-01-17"]
        assert (rows[1].samples, rows[1].coverage) == (0, 0.0)
        assert rows[1].values == {TEMPERATURE: None, PRESSURE: None, SPEED: None}

    def test_no_observations_at_all(self) -> None:
        rows = aggregate([], Aggregation.HOURLY, "2026-01-15T10:00:00", "2026-01-15T12:00:00")

        assert [row.samples for row in rows] == [0, 0, 0]

    def test_monthly_expected_samples_follow_the_length_of_each_month(self) -> None:
        rows = aggregate([], Aggregation.MONTHLY, "2026-01-15T03:00:00", "2026-02-15T03:00:00")

        assert [(row.period, row.expected_samples) for row in rows] == [
            ("2026-01", 31 * 144),
            ("2026-02", 28 * 144),
        ]


# This property checks correctness, not speed: pandas' first call is slow (lazy imports), which
# would trip Hypothesis' default per-example deadline and make the test flaky.
@settings(deadline=None, max_examples=50)
@given(
    slots=st.dictionaries(
        keys=st.integers(min_value=0, max_value=3 * 144 - 1),  # three days of 10-minute slots
        values=st.one_of(st.none(), st.floats(min_value=-40, max_value=20)),
        max_size=300,
    ),
    aggregation=st.sampled_from([Aggregation.HOURLY, Aggregation.DAILY, Aggregation.MONTHLY]),
)
def test_no_observation_is_lost_or_counted_twice(
    slots: dict[int, float | None], aggregation: Aggregation
) -> None:
    first = utc("2026-01-01T00:00:00")
    observations = [
        Observation(first + timedelta(minutes=10 * slot), temperature, None, None)
        for slot, temperature in sorted(slots.items())
    ]

    rows = aggregate(
        observations, aggregation, "2026-01-01T00:00:00", "2026-01-03T23:50:00", [TEMPERATURE]
    )

    assert sum(row.samples or 0 for row in rows) == sum(
        1 for obs in observations if obs.temperature is not None
    )
