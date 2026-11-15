"""DST test suite, input side: local times around the Europe/Madrid clock changes of 2026.

- Spring forward, 2026-03-29: at 02:00 the clocks jump to 03:00, so 02:00-02:59 does not exist.
- Fall back, 2026-10-25: at 03:00 the clocks go back to 02:00, so 02:00-02:59 happens twice.

Policy: such local times are rejected (HTTP 422 at the API level); an explicit offset always
selects a single instant.
"""

from datetime import UTC, datetime

import pytest

from app.core.exceptions import AmbiguousLocalTimeError, NonExistentLocalTimeError
from app.domain.time_range import resolve_range

FAR_END = "2027-01-01T00:00:00"  # a valid end in every zone used below


def resolve_start(start: str, tz: str | None = None) -> datetime:
    return resolve_range(start, FAR_END, tz).start


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class TestSpringForward:
    @pytest.mark.parametrize(
        "local", ["2026-03-29T02:00:00", "2026-03-29T02:30:00", "2026-03-29T02:59:59"]
    )
    def test_skipped_local_time_is_rejected(self, local: str) -> None:
        with pytest.raises(NonExistentLocalTimeError) as excinfo:
            resolve_start(local)

        assert excinfo.value.parameter == "start"
        assert "does not exist in Europe/Madrid" in excinfo.value.message

    @pytest.mark.parametrize(
        ("local", "expected_utc"),
        [
            ("2026-03-29T01:59:59", "2026-03-29T00:59:59"),  # last second before the jump (+01:00)
            ("2026-03-29T03:00:00", "2026-03-29T01:00:00"),  # first second after the jump (+02:00)
        ],
    )
    def test_times_around_the_gap_are_valid(self, local: str, expected_utc: str) -> None:
        assert resolve_start(local) == utc(expected_utc)

    def test_explicit_offset_defines_a_real_instant(self) -> None:
        assert resolve_start("2026-03-29T02:30:00", tz="+01:00") == utc("2026-03-29T01:30:00")

    def test_rejected_end_reports_the_end_parameter(self) -> None:
        with pytest.raises(NonExistentLocalTimeError) as excinfo:
            resolve_range("2026-03-28T00:00:00", "2026-03-29T02:30:00", None)

        assert excinfo.value.parameter == "end"


class TestFallBack:
    @pytest.mark.parametrize(
        "local", ["2026-10-25T02:00:00", "2026-10-25T02:30:00", "2026-10-25T02:59:59"]
    )
    def test_repeated_local_time_is_rejected(self, local: str) -> None:
        with pytest.raises(AmbiguousLocalTimeError) as excinfo:
            resolve_start(local)

        assert excinfo.value.parameter == "start"
        assert "+02:00 for the first occurrence" in excinfo.value.message
        assert "+01:00 for the second" in excinfo.value.message

    @pytest.mark.parametrize(
        ("tz", "expected_utc"),
        [("+02:00", "2026-10-25T00:30:00"), ("+01:00", "2026-10-25T01:30:00")],
    )
    def test_explicit_offset_selects_one_occurrence(self, tz: str, expected_utc: str) -> None:
        assert resolve_start("2026-10-25T02:30:00", tz=tz) == utc(expected_utc)

    def test_offset_embedded_in_the_datetime_also_disambiguates(self) -> None:
        time_range = resolve_range("2026-10-25T02:30:00+01:00", "2026-10-26T00:00:00+01:00", None)

        assert time_range.start == utc("2026-10-25T01:30:00")

    @pytest.mark.parametrize(
        ("local", "expected_utc"),
        [
            ("2026-10-25T01:59:59", "2026-10-24T23:59:59"),  # still summer time (+02:00)
            ("2026-10-25T03:00:00", "2026-10-25T02:00:00"),  # already winter time (+01:00)
        ],
    )
    def test_times_around_the_overlap_are_valid(self, local: str, expected_utc: str) -> None:
        assert resolve_start(local) == utc(expected_utc)


class TestOtherZones:
    def test_policy_applies_to_any_iana_zone(self) -> None:
        with pytest.raises(AmbiguousLocalTimeError):
            resolve_start("2026-10-25T02:30:00", tz="Europe/Berlin")
        with pytest.raises(NonExistentLocalTimeError):  # US spring forward: 8 March 2026
            resolve_start("2026-03-08T02:30:00", tz="America/New_York")

    def test_fixed_offsets_have_no_gaps_or_overlaps(self) -> None:
        assert resolve_start("2026-10-25T02:30:00", tz="-03:00") == utc("2026-10-25T05:30:00")
