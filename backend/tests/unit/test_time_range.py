"""Unit tests for resolving and validating the requested time range."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import InvalidParameterError, RangeTooLargeError
from app.domain.measurements import Aggregation
from app.domain.time_range import TimeRange, resolve_range, validate_range_length


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class TestInterpretation:
    def test_naive_datetimes_default_to_madrid_time(self) -> None:
        time_range = resolve_range("2026-01-15T00:00:00", "2026-07-15T00:00:00", None)

        assert time_range.start == utc("2026-01-14T23:00:00")  # winter, +01:00
        assert time_range.end == utc("2026-07-14T22:00:00")  # summer, +02:00
        assert time_range.input_interpretation == "Europe/Madrid (default)"

    def test_tz_parameter_with_an_iana_name(self) -> None:
        time_range = resolve_range("2026-01-15T00:00:00", "2026-01-16T00:00:00", "Europe/London")

        assert time_range.start == utc("2026-01-15T00:00:00")
        assert time_range.input_interpretation == "Europe/London (tz parameter)"

    def test_tz_parameter_with_an_offset(self) -> None:
        time_range = resolve_range("2026-01-15T00:00:00", "2026-01-16T00:00:00", "+05:30")

        assert time_range.start == utc("2026-01-14T18:30:00")
        assert time_range.input_interpretation == "+05:30 (tz parameter)"

    def test_offsets_embedded_in_the_datetimes(self) -> None:
        time_range = resolve_range("2026-01-15T00:00:00Z", "2026-01-16T00:00:00Z", None)

        assert time_range.start == utc("2026-01-15T00:00:00")
        assert time_range.input_interpretation == "UTC (embedded in the datetime)"

    def test_different_interpretations_are_described_separately(self) -> None:
        time_range = resolve_range("2026-01-15T00:00:00+02:00", "2026-01-16T00:00:00", None)

        assert time_range.input_interpretation == (
            "start: +02:00 (embedded in the datetime); end: Europe/Madrid (default)"
        )

    def test_plus_sign_decoded_as_space_is_restored(self) -> None:
        time_range = resolve_range("2026-01-15T00:00:00 02:00", "2026-01-16T00:00:00 02:00", None)

        assert time_range.start == utc("2026-01-14T22:00:00")


class TestValidation:
    def test_tz_and_embedded_offset_together_are_a_conflict(self) -> None:
        with pytest.raises(InvalidParameterError, match="not both") as excinfo:
            resolve_range("2026-01-15T00:00:00+02:00", "2026-01-16T00:00:00", "Europe/Madrid")

        assert excinfo.value.parameter == "tz"

    @pytest.mark.parametrize(
        "value",
        [
            "2026-01-15",
            "2026-01-15T00:00",
            "15/01/2026 00:00:00",
            "2026-01-15 00:00:00",
            "2026-01-15T00:00:00.123",
            "2026-01-15T00:00:00+2",
        ],
    )
    def test_malformed_datetimes_are_rejected(self, value: str) -> None:
        with pytest.raises(InvalidParameterError, match="not a valid datetime") as excinfo:
            resolve_range(value, "2026-02-01T00:00:00", None)

        assert excinfo.value.parameter == "start"

    @pytest.mark.parametrize("value", ["2026-02-30T00:00:00", "2026-01-15T24:00:00"])
    def test_impossible_calendar_values_are_rejected(self, value: str) -> None:
        with pytest.raises(InvalidParameterError, match="not a valid calendar date or time"):
            resolve_range(value, "2027-01-01T00:00:00", None)

    @pytest.mark.parametrize("end", ["2026-01-15T00:00:00", "2026-01-14T23:50:00"])
    def test_end_must_be_later_than_start(self, end: str) -> None:
        with pytest.raises(InvalidParameterError, match="later than start") as excinfo:
            resolve_range("2026-01-15T00:00:00", end, None)

        assert excinfo.value.parameter == "end"


class TestRangeLength:
    @staticmethod
    def make_range(days: float) -> TimeRange:
        start = utc("2026-01-01T00:00:00")
        return TimeRange(start, start + timedelta(days=days), "UTC (embedded in the datetime)")

    def test_range_at_the_limit_is_accepted(self) -> None:
        validate_range_length(self.make_range(31), Aggregation.NONE, max_days=31)

    def test_range_over_the_limit_suggests_coarser_aggregations(self) -> None:
        with pytest.raises(RangeTooLargeError) as excinfo:
            validate_range_length(self.make_range(31.01), Aggregation.NONE, max_days=31)

        assert "maximum for aggregation=none" in excinfo.value.message
        assert "(hourly, daily, monthly)" in excinfo.value.message

    def test_coarsest_level_only_suggests_reducing_the_range(self) -> None:
        with pytest.raises(RangeTooLargeError) as excinfo:
            validate_range_length(self.make_range(400), Aggregation.MONTHLY, max_days=365)

        assert excinfo.value.message.endswith("Reduce the range.")

    def test_no_limit_means_any_range_is_accepted(self) -> None:
        validate_range_length(self.make_range(36_500), Aggregation.MONTHLY, max_days=None)

    def test_31_calendar_days_across_the_autumn_change_exceed_31_days(self) -> None:
        # Madrid falls back on 2025-10-26: the clock repeats one hour, so the range lasts 1 h more.
        time_range = resolve_range("2025-10-01T00:00:00", "2025-11-01T00:00:00", None)

        assert time_range.end - time_range.start == timedelta(days=31, hours=1)
        with pytest.raises(RangeTooLargeError):
            validate_range_length(time_range, Aggregation.NONE, max_days=31)

    def test_range_that_looks_longer_across_the_spring_change_is_accepted(self) -> None:
        # Madrid springs forward on 2025-03-30: the clock skips one hour, so the range lasts 1 h
        # less than the 31 days and 30 minutes its dates suggest.
        time_range = resolve_range("2025-03-01T00:00:00", "2025-04-01T00:30:00", None)

        assert time_range.end - time_range.start == timedelta(days=30, hours=23, minutes=30)
        validate_range_length(time_range, Aggregation.NONE, max_days=31)
