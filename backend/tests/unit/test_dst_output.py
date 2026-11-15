"""DST test suite, output side: datetimes written in Europe/Madrid around the 2026 clock changes."""

from datetime import UTC, datetime, timedelta

from app.domain.timezones import format_output_datetime


def ten_minute_grid(start_utc: str, count: int) -> list[datetime]:
    first = datetime.fromisoformat(start_utc).replace(tzinfo=UTC)
    return [first + timedelta(minutes=10 * step) for step in range(count)]


def test_offset_switches_to_summer_time_at_spring_forward() -> None:
    # 2026-03-29: 00:50Z is 01:50+01:00 and 01:00Z is already 03:00+02:00 (no 02:xx local times).
    written = [format_output_datetime(t) for t in ten_minute_grid("2026-03-29T00:40:00", 4)]

    assert written == [
        "2026-03-29T01:40:00+01:00",
        "2026-03-29T01:50:00+01:00",
        "2026-03-29T03:00:00+02:00",
        "2026-03-29T03:10:00+02:00",
    ]


def test_repeated_hour_at_fall_back_is_written_with_two_different_offsets() -> None:
    # 2026-10-25: 00:00Z-00:50Z and 01:00Z-01:50Z both show 02:xx on Madrid clocks.
    instants = ten_minute_grid("2026-10-25T00:00:00", 12)
    written = [format_output_datetime(t) for t in instants]

    assert written[:2] == ["2026-10-25T02:00:00+02:00", "2026-10-25T02:10:00+02:00"]
    assert written[6:8] == ["2026-10-25T02:00:00+01:00", "2026-10-25T02:10:00+01:00"]
    # The wall-clock times repeat, but every written value is distinct and parses back to its
    # own instant: no timestamp is duplicated or lost.
    assert len(set(written)) == len(written)
    assert [datetime.fromisoformat(text) for text in written] == instants


def test_winter_and_summer_offsets() -> None:
    assert format_output_datetime(datetime(2026, 1, 15, tzinfo=UTC)) == "2026-01-15T01:00:00+01:00"
    assert format_output_datetime(datetime(2026, 7, 15, tzinfo=UTC)) == "2026-07-15T02:00:00+02:00"
