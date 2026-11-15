"""Splitting of time ranges into calendar months in UTC.

AEMET accepts at most one month per request, and the cache stores data in the same monthly
chunks, so both rely on this single definition.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class MonthChunk:
    """One calendar month in UTC. Both ends are inclusive."""

    key: str
    """Year and month, e.g. ``"2026-01"``."""
    start: datetime
    """First instant of the month."""
    end: datetime
    """Last second of the month (the next month starts one second later)."""


def month_chunks(start: datetime, end: datetime) -> list[MonthChunk]:
    """Return every calendar month (in UTC) that overlaps the inclusive range ``[start, end]``."""
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Naive datetimes are not allowed.")
    chunks: list[MonthChunk] = []
    month_start = start.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while month_start <= end:
        next_month = _next_month(month_start)
        chunks.append(
            MonthChunk(
                key=f"{month_start:%Y-%m}",
                start=month_start,
                end=next_month - timedelta(seconds=1),
            )
        )
        month_start = next_month
    return chunks


def _next_month(month_start: datetime) -> datetime:
    if month_start.month == 12:
        return month_start.replace(year=month_start.year + 1, month=1)
    return month_start.replace(month=month_start.month + 1)
