"""Tests of the cache-first measurement service: a counting fake source, a controllable clock and
the real SQLite repository on a temporary file."""

import threading
import time
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.core.exceptions import UpstreamCoolingDownError, UpstreamUnavailableError
from app.db.database import open_database
from app.db.repository import CacheRepository
from app.domain.chunks import CachedChunk
from app.domain.freshness import CacheReport, FreshnessPolicy
from app.domain.measurements import Aggregation, MeasurementType, Observation
from app.domain.stations import Station, get_station
from app.domain.time_range import TimeRange
from app.services.coalescing import SingleFlight
from app.services.measurements import (
    MeasurementQuery,
    MeasurementResult,
    MeasurementService,
    MonthKey,
)

STATION = get_station("juan-carlos-i")
POLICY = FreshnessPolicy(ttl=timedelta(hours=1), grace=timedelta(hours=48))
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
TIMEOUT = 5.0

Flights = SingleFlight[MonthKey, tuple[CachedChunk, bool]]


def at(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


class CountingSource:
    """In-memory ``WeatherSource`` that records every call."""

    def __init__(self) -> None:
        self.observations: list[Observation] = []
        self.calls: list[tuple[datetime, datetime]] = []
        self.error: Exception | None = None
        self.during_fetch: Callable[[], None] | None = None

    def fetch(self, station: Station, start: datetime, end: datetime) -> list[Observation]:
        self.calls.append((start, end))
        if self.during_fetch is not None:
            self.during_fetch()
        if self.error is not None:
            raise self.error
        return [o for o in self.observations if start <= o.timestamp <= end]


def grid(start: str, count: int) -> list[Observation]:
    first = at(start)
    return [Observation(first + timedelta(minutes=10 * i), 1.0, 980.0, 5.0) for i in range(count)]


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = open_database(tmp_path / "cache.sqlite3", data_source="aemet")
    yield engine
    engine.dispose()


@pytest.fixture
def repository(engine: Engine) -> CacheRepository:
    return CacheRepository(engine)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(NOW)


@pytest.fixture
def source() -> CountingSource:
    return CountingSource()


@pytest.fixture
def flights() -> Flights:
    return SingleFlight()


@pytest.fixture
def service(
    source: CountingSource, repository: CacheRepository, clock: FakeClock, flights: Flights
) -> MeasurementService:
    return MeasurementService(source, "aemet", repository, POLICY, clock=clock, flights=flights)


def get(service: MeasurementService, start: str, end: str) -> MeasurementResult:
    query = MeasurementQuery(
        station=STATION,
        time_range=TimeRange(start=at(start), end=at(end), input_interpretation="UTC"),
        aggregation=Aggregation.NONE,
        types=tuple(MeasurementType),
    )
    return service.get(query)


def test_whole_months_are_fetched_once_and_then_served_from_the_cache(
    service: MeasurementService, source: CountingSource
) -> None:
    source.observations = grid("2026-01-15T00:00:00", 144)

    first = get(service, "2026-01-15T10:00:00", "2026-01-15T11:00:00")
    second = get(service, "2026-01-15T10:00:00", "2026-01-15T11:00:00")

    assert source.calls == [(at("2026-01-01T00:00:00"), at("2026-01-31T23:59:59"))]
    assert first.cache == CacheReport("miss", None)  # January is final: nothing can change
    assert second.cache == CacheReport("hit", None)
    # The whole month is cached, but only the requested range is returned.
    assert first.observation_count == second.observation_count == 7


def test_responses_come_from_the_cache_not_from_the_source(
    service: MeasurementService, source: CountingSource
) -> None:
    source.observations = grid("2026-01-15T10:00:00", 3)
    get(service, "2026-01-15T10:00:00", "2026-01-15T11:00:00")
    source.observations = []

    assert get(service, "2026-01-15T10:00:00", "2026-01-15T11:00:00").observation_count == 3


def test_the_month_in_progress_is_fetched_up_to_now_and_expires_after_the_ttl(
    service: MeasurementService, source: CountingSource, clock: FakeClock
) -> None:
    first = get(service, "2026-10-31T12:00:00", "2026-11-02T12:00:00")

    assert source.calls == [
        (at("2026-10-01T00:00:00"), at("2026-10-31T23:59:59")),
        (at("2026-11-01T00:00:00"), NOW),
    ]
    assert first.cache == CacheReport("miss", NOW)  # October is final, November is not

    clock.advance(timedelta(minutes=59))
    assert get(service, "2026-10-31T12:00:00", "2026-11-02T12:00:00").cache == CacheReport(
        "hit", NOW
    )

    clock.advance(timedelta(minutes=1))
    third = get(service, "2026-10-31T12:00:00", "2026-11-02T12:00:00")

    assert source.calls[2:] == [(at("2026-11-01T00:00:00"), NOW + timedelta(hours=1))]
    assert third.cache == CacheReport("partial", NOW + timedelta(hours=1))


def test_a_recently_ended_month_is_fetched_again_until_it_becomes_final(
    service: MeasurementService, source: CountingSource, clock: FakeClock
) -> None:
    clock.now = at("2026-11-01T12:00:00")  # October ended 12 hours ago
    assert get(service, "2026-10-10T00:00:00", "2026-10-11T00:00:00").cache == CacheReport(
        "miss", at("2026-11-01T12:00:00")
    )

    clock.now = at("2026-11-03T00:00:00")  # 48 hours after the end of October
    assert get(service, "2026-10-10T00:00:00", "2026-10-11T00:00:00").cache == CacheReport(
        "miss", None
    )

    clock.now = at("2026-12-25T00:00:00")
    assert get(service, "2026-10-10T00:00:00", "2026-10-11T00:00:00").cache == CacheReport(
        "hit", None
    )
    assert len(source.calls) == 2


def test_a_final_month_without_data_is_not_requested_again(
    service: MeasurementService, source: CountingSource
) -> None:
    first = get(service, "2026-01-15T00:00:00", "2026-01-16T00:00:00")
    second = get(service, "2026-01-15T00:00:00", "2026-01-16T00:00:00")

    assert (first.observation_count, second.observation_count) == (0, 0)
    assert second.cache.status == "hit"
    assert len(source.calls) == 1


def test_months_in_the_future_are_neither_fetched_nor_stored(
    service: MeasurementService, source: CountingSource, repository: CacheRepository
) -> None:
    get(service, "2026-11-20T00:00:00", "2026-12-10T00:00:00")
    future_only = get(service, "2027-01-01T00:00:00", "2027-01-02T00:00:00")

    assert source.calls == [(at("2026-11-01T00:00:00"), NOW)]
    assert set(repository.cached_chunks(STATION.id, ["2026-11", "2026-12", "2027-01"])) == {
        "2026-11"
    }
    assert future_only.cache == CacheReport("hit", None)


def test_the_fetch_time_is_the_start_of_the_request(
    service: MeasurementService,
    source: CountingSource,
    repository: CacheRepository,
    clock: FakeClock,
) -> None:
    # A slow fetch: the data may miss anything published while it ran, so the earlier instant
    # is the honest one. Fractions of a second are dropped.
    clock.now = NOW + timedelta(microseconds=500_000)
    source.during_fetch = lambda: clock.advance(timedelta(seconds=20))

    result = get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")

    assert repository.cached_chunks(STATION.id, ["2026-11"])["2026-11"].fetched_at == NOW
    assert result.cache.last_updated == NOW


def test_a_failed_fetch_stores_nothing_and_reaches_the_caller(
    service: MeasurementService, source: CountingSource, repository: CacheRepository
) -> None:
    source.error = UpstreamUnavailableError("AEMET could not be reached.")

    with pytest.raises(UpstreamUnavailableError):
        get(service, "2026-01-15T00:00:00", "2026-01-16T00:00:00")

    assert repository.cached_chunks(STATION.id, ["2026-01"]) == {}


# Concurrent requests. The first fetch is held until every other request is waiting for it, so
# the tests never depend on timing.


def wait_until(condition: Callable[[], bool]) -> None:
    deadline = time.monotonic() + TIMEOUT
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("Condition not reached in time.")
        time.sleep(0.005)


def request_concurrently(
    service: MeasurementService,
    source: CountingSource,
    flights: Flights,
    requests: int,
    day: str = "2026-01-15",
) -> list[MeasurementResult | BaseException]:
    """Send ``requests`` concurrent requests for the first hour of ``day``."""
    started, release = threading.Event(), threading.Event()

    def hold_the_fetch() -> None:
        started.set()
        if not release.wait(TIMEOUT):
            raise AssertionError("The fetch was never released.")

    source.during_fetch = hold_the_fetch
    outcomes: list[MeasurementResult | BaseException] = []

    def request() -> None:
        try:
            outcomes.append(get(service, f"{day}T00:00:00", f"{day}T01:00:00"))
        except BaseException as error:
            outcomes.append(error)

    first = threading.Thread(target=request)
    first.start()
    assert started.wait(TIMEOUT)
    others = [threading.Thread(target=request) for _ in range(requests - 1)]
    for thread in others:
        thread.start()
    wait_until(lambda: flights.waiting((STATION.id, day[:7])) == requests - 1)
    release.set()
    for thread in [first, *others]:
        thread.join(TIMEOUT)
    return outcomes


def test_concurrent_requests_for_the_same_month_share_one_fetch(
    service: MeasurementService, source: CountingSource, flights: Flights
) -> None:
    source.observations = grid("2026-01-15T00:00:00", 144)

    outcomes = request_concurrently(service, source, flights, requests=10)

    assert len(source.calls) == 1
    assert all(isinstance(outcome, MeasurementResult) for outcome in outcomes)
    results = [outcome for outcome in outcomes if isinstance(outcome, MeasurementResult)]
    assert [result.observation_count for result in results] == [7] * 10
    # Every request waited for the fetch, so every one of them reports it.
    assert [result.cache.status for result in results] == ["miss"] * 10


def test_a_failed_fetch_reaches_every_waiting_request_without_being_repeated(
    service: MeasurementService,
    source: CountingSource,
    flights: Flights,
    repository: CacheRepository,
) -> None:
    error = UpstreamUnavailableError("AEMET could not be reached.")
    source.error = error

    outcomes = request_concurrently(service, source, flights, requests=10)

    assert outcomes == [error] * 10
    assert len(source.calls) == 1
    assert repository.cached_chunks(STATION.id, ["2026-01"]) == {}


def test_different_months_are_fetched_at_the_same_time(
    service: MeasurementService, source: CountingSource
) -> None:
    # Each fetch waits for the other one: if months were fetched one at a time, the barrier
    # would time out and both requests would fail.
    both_fetching = threading.Barrier(2, timeout=TIMEOUT)

    def wait_for_the_other_fetch() -> None:
        both_fetching.wait()

    source.during_fetch = wait_for_the_other_fetch
    outcomes: list[MeasurementResult | BaseException] = []

    def request(start: str, end: str) -> None:
        try:
            outcomes.append(get(service, start, end))
        except BaseException as error:
            outcomes.append(error)

    threads = [
        threading.Thread(target=request, args=("2026-01-15T00:00:00", "2026-01-16T00:00:00")),
        threading.Thread(target=request, args=("2026-02-15T00:00:00", "2026-02-16T00:00:00")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(TIMEOUT)

    assert all(isinstance(outcome, MeasurementResult) for outcome in outcomes), outcomes
    assert len(source.calls) == 2


def test_a_month_stored_after_the_first_check_is_not_fetched_again(
    service: MeasurementService,
    source: CountingSource,
    repository: CacheRepository,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get(service, "2026-01-15T00:00:00", "2026-01-16T00:00:00")
    # The next request's first check sees an outdated view (as if another request were storing
    # January at that very moment); the second check, inside the coordinated fetch, sees it.
    real_cached_chunks = repository.cached_chunks
    views: list[str] = []

    def outdated_first_view(station_id: str, keys: list[str]) -> dict[str, CachedChunk]:
        views.append("first" if not views else "second")
        return {} if len(views) == 1 else real_cached_chunks(station_id, keys)

    monkeypatch.setattr(repository, "cached_chunks", outdated_first_view)

    result = get(service, "2026-01-15T00:00:00", "2026-01-16T00:00:00")

    assert views == ["first", "second"]
    assert result.cache.status == "hit"
    assert len(source.calls) == 1


# AEMET failures with a cached copy: stale data and the circuit breaker (60-second cool-down).


def cache_november_then_fail(
    service: MeasurementService, source: CountingSource, clock: FakeClock
) -> None:
    """Cache November at NOW, let it expire and make the source fail."""
    source.observations = grid("2026-11-10T00:00:00", 6)
    get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")
    clock.advance(timedelta(hours=2))
    source.error = UpstreamUnavailableError("AEMET could not be reached.")


def test_an_expired_month_is_served_stale_when_the_fetch_fails(
    service: MeasurementService,
    source: CountingSource,
    clock: FakeClock,
    repository: CacheRepository,
) -> None:
    cache_november_then_fail(service, source, clock)

    result = get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")

    assert result.cache == CacheReport("hit", NOW, stale=True)
    assert result.observation_count == 6
    assert len(source.calls) == 2  # the refresh was attempted
    assert repository.cached_chunks(STATION.id, ["2026-11"])["2026-11"].fetched_at == NOW


def test_while_cooling_down_the_source_is_not_called(
    service: MeasurementService, source: CountingSource, clock: FakeClock
) -> None:
    cache_november_then_fail(service, source, clock)
    get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")  # fails and opens the circuit
    clock.advance(timedelta(seconds=10))

    stale = get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")
    with pytest.raises(UpstreamCoolingDownError) as no_copy:
        get(service, "2026-09-10T00:00:00", "2026-09-11T00:00:00")

    assert stale.cache.stale
    assert no_copy.value.retry_after_seconds == 50
    assert len(source.calls) == 2  # neither request reached the source


def test_final_months_are_unaffected_while_cooling_down(
    service: MeasurementService, source: CountingSource, clock: FakeClock
) -> None:
    get(service, "2026-01-15T00:00:00", "2026-01-16T00:00:00")
    cache_november_then_fail(service, source, clock)
    get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")  # opens the circuit

    result = get(service, "2026-01-15T00:00:00", "2026-01-16T00:00:00")

    assert result.cache == CacheReport("hit", None, stale=False)


def test_after_the_cooldown_the_source_is_tried_again(
    service: MeasurementService, source: CountingSource, clock: FakeClock
) -> None:
    cache_november_then_fail(service, source, clock)
    get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")  # opens the circuit
    clock.advance(timedelta(seconds=60))
    source.error = None  # AEMET is back

    result = get(service, "2026-11-10T00:00:00", "2026-11-11T00:00:00")

    assert result.cache == CacheReport("miss", clock.now, stale=False)
    assert len(source.calls) == 3


def test_concurrent_requests_all_get_the_stale_copy_after_one_failed_fetch(
    service: MeasurementService, source: CountingSource, clock: FakeClock, flights: Flights
) -> None:
    cache_november_then_fail(service, source, clock)

    outcomes = request_concurrently(service, source, flights, requests=10, day="2026-11-10")

    results = [outcome for outcome in outcomes if isinstance(outcome, MeasurementResult)]
    assert len(results) == 10, outcomes
    assert all(result.cache.stale for result in results)
    assert len(source.calls) == 2  # the first caching fetch and one shared failed refresh
