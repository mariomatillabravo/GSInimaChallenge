"""DST test suite, aggregated output: buckets around the Europe/Madrid clock changes of 2026.

Station local time is a fixed UTC-03:00, so every station day has 144 ten-minute slots: Madrid's
DST never shortens or lengthens a bucket. It only changes how bucket labels are written in
Europe/Madrid, which the tests check through the same formatter used by the API.
"""

from datetime import UTC, datetime, timedelta

from app.domain.aggregation import SeriesRow, build_series
from app.domain.measurements import Aggregation, MeasurementType, Observation
from app.domain.stations import ANTARCTIC_STATION_TIME
from app.domain.timezones import format_output_datetime

TEMPERATURE = MeasurementType.TEMPERATURE


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def grid(start: str, count: int) -> list[Observation]:
    first = utc(start)
    return [
        Observation(first + timedelta(minutes=10 * step), float(step), None, None)
        for step in range(count)
    ]


def aggregate(
    observations: list[Observation], aggregation: Aggregation, start: str, end: str
) -> list[SeriesRow]:
    return build_series(
        observations,
        aggregation=aggregation,
        types=[TEMPERATURE],
        station_timezone=ANTARCTIC_STATION_TIME,
        start=utc(start),
        end=utc(end),
    )


def labels(rows: list[SeriesRow]) -> list[str]:
    return [format_output_datetime(row.timestamp) for row in rows]


class TestHourly:
    def test_fall_back_shows_the_repeated_hour_twice_with_different_offsets(self) -> None:
        rows = aggregate(
            grid("2026-10-24T23:00:00", 24),
            Aggregation.HOURLY,
            "2026-10-24T23:00:00",
            "2026-10-25T02:50:00",
        )

        assert labels(rows) == [
            "2026-10-25T01:00:00+02:00",
            "2026-10-25T02:00:00+02:00",
            "2026-10-25T02:00:00+01:00",
            "2026-10-25T03:00:00+01:00",
        ]
        assert [row.samples for row in rows] == [6, 6, 6, 6]
        assert [row.values[TEMPERATURE] for row in rows] == [2.5, 8.5, 14.5, 20.5]

    def test_spring_forward_has_no_two_oclock_bucket_and_loses_no_data(self) -> None:
        rows = aggregate(
            grid("2026-03-29T00:00:00", 12),
            Aggregation.HOURLY,
            "2026-03-29T00:00:00",
            "2026-03-29T01:50:00",
        )

        assert labels(rows) == ["2026-03-29T01:00:00+01:00", "2026-03-29T03:00:00+02:00"]
        assert [row.samples for row in rows] == [6, 6]


class TestDaily:
    def test_station_days_around_spring_forward_are_complete(self) -> None:
        rows = aggregate(
            grid("2026-03-28T03:00:00", 288),
            Aggregation.DAILY,
            "2026-03-28T03:00:00",
            "2026-03-30T02:50:00",
        )

        assert [row.period for row in rows] == ["2026-03-28", "2026-03-29"]
        assert labels(rows) == ["2026-03-28T04:00:00+01:00", "2026-03-29T05:00:00+02:00"]
        assert [(row.expected_samples, row.coverage) for row in rows] == [(144, 100.0)] * 2

    def test_station_days_around_fall_back_are_not_25_hours_long(self) -> None:
        rows = aggregate(
            grid("2026-10-24T03:00:00", 288),
            Aggregation.DAILY,
            "2026-10-24T03:00:00",
            "2026-10-26T02:50:00",
        )

        assert labels(rows) == ["2026-10-24T05:00:00+02:00", "2026-10-25T04:00:00+01:00"]
        assert [(row.expected_samples, row.coverage) for row in rows] == [(144, 100.0)] * 2

    def test_observation_after_utc_midnight_belongs_to_the_previous_station_day(self) -> None:
        # 2026-07-10T02:30Z is 2026-07-09T23:30 at the station (UTC-03:00).
        [row] = aggregate(
            [Observation(utc("2026-07-10T02:30:00"), 1.0, None, None)],
            Aggregation.DAILY,
            "2026-07-10T02:30:00",
            "2026-07-10T02:30:00",
        )

        assert row.period == "2026-07-09"
        assert labels([row]) == ["2026-07-09T05:00:00+02:00"]


def test_monthly_bucket_label() -> None:
    [row] = aggregate(
        grid("2026-03-01T03:00:00", 6),
        Aggregation.MONTHLY,
        "2026-03-01T03:00:00",
        "2026-03-01T03:50:00",
    )

    assert row.period == "2026-03"
    assert labels([row]) == ["2026-03-01T04:00:00+01:00"]
    assert row.expected_samples == 31 * 144
