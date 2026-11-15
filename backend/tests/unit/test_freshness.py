"""Unit tests of the freshness rules of the cache (one hour TTL, 48 hours grace)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.domain.chunks import CachedChunk, MonthChunk, month_chunks
from app.domain.freshness import (
    CacheReport,
    FreshnessPolicy,
    MonthState,
    is_final,
    needs_fetch,
    summarize,
)

POLICY = FreshnessPolicy(ttl=timedelta(hours=1), grace=timedelta(hours=48))
SECOND = timedelta(seconds=1)


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


def month(key: str) -> MonthChunk:
    return month_chunks(at(f"{key}-01T00:00:00"), at(f"{key}-01T00:00:00"))[0]


JANUARY = month("2026-01")
JANUARY_FINAL_FROM = at("2026-02-03T00:00:00")
"""January ends at 2026-02-01T00:00:00Z; 48 hours later its data counts as final."""


def cached(fetched_at: datetime, key: str = "2026-01", row_count: int = 10) -> CachedChunk:
    return CachedChunk(key=key, fetched_at=fetched_at, row_count=row_count)


def test_a_month_not_in_the_cache_is_fetched() -> None:
    assert needs_fetch(JANUARY, None, at("2026-01-15T00:00:00"), POLICY)


@pytest.mark.parametrize(
    ("fetched_at", "final"),
    [
        (at("2026-01-20T00:00:00"), False),  # while the month was in progress
        (at("2026-02-01T10:00:00"), False),  # right after it ended
        (JANUARY_FINAL_FROM - SECOND, False),
        (JANUARY_FINAL_FROM, True),  # exactly 48 hours after the end
        (at("2026-11-15T12:00:00"), True),
    ],
)
def test_a_month_is_final_once_fetched_48_hours_after_its_end(
    fetched_at: datetime, final: bool
) -> None:
    assert is_final(JANUARY, cached(fetched_at), POLICY) is final


def test_a_final_month_is_never_fetched_again() -> None:
    entry = cached(JANUARY_FINAL_FROM)

    assert not needs_fetch(JANUARY, entry, at("2036-01-01T00:00:00"), POLICY)


@pytest.mark.parametrize(
    ("age", "fetch"),
    [
        (timedelta(0), False),
        (timedelta(minutes=59, seconds=59), False),
        (timedelta(hours=1), True),  # the TTL is not inclusive
        (timedelta(days=3), True),
    ],
)
def test_a_month_that_can_still_change_expires_after_the_ttl(age: timedelta, fetch: bool) -> None:
    fetched_at = at("2026-01-20T00:00:00")

    assert needs_fetch(JANUARY, cached(fetched_at), fetched_at + age, POLICY) is fetch


def test_example_from_the_documentation() -> None:
    # January fetched on 1 February at 10:00 is not final yet: on 5 February it has expired and is
    # fetched again; that copy is final, so on 6 February nothing is fetched.
    first = cached(at("2026-02-01T10:00:00"))
    assert needs_fetch(JANUARY, first, at("2026-02-05T09:00:00"), POLICY)

    second = cached(at("2026-02-05T09:00:00"))
    assert not needs_fetch(JANUARY, second, at("2026-02-06T09:00:00"), POLICY)


def state(key: str, fetched_at: datetime, fetched_now: bool) -> MonthState:
    return MonthState(month(key), cached(fetched_at, key=key), fetched_now)


NOW = at("2026-11-15T12:00:00")
OCTOBER_FINAL = state("2026-10", at("2026-11-10T00:00:00"), fetched_now=False)
NOVEMBER_FRESH = state("2026-11", NOW - timedelta(minutes=20), fetched_now=False)
NOVEMBER_FETCHED = state("2026-11", NOW, fetched_now=True)


@pytest.mark.parametrize(
    ("months", "expected"),
    [
        ([OCTOBER_FINAL, NOVEMBER_FRESH], CacheReport("hit", NOW - timedelta(minutes=20))),
        ([NOVEMBER_FETCHED], CacheReport("miss", NOW)),
        ([OCTOBER_FINAL, NOVEMBER_FETCHED], CacheReport("partial", NOW)),
        ([OCTOBER_FINAL], CacheReport("hit", None)),  # all final: nothing can change
        ([], CacheReport("hit", None)),  # e.g. a range entirely in the future
    ],
)
def test_summary_of_a_request(months: list[MonthState], expected: CacheReport) -> None:
    assert summarize(months, POLICY) == expected


def test_last_updated_is_the_oldest_fetch_among_months_that_can_still_change() -> None:
    september_recent = state("2026-09", at("2026-10-01T06:00:00"), fetched_now=False)
    policy = FreshnessPolicy(ttl=timedelta(days=60), grace=timedelta(days=30))

    report = summarize([september_recent, NOVEMBER_FETCHED], policy)

    assert report.last_updated == at("2026-10-01T06:00:00")
