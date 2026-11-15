"""Tests of the cache-first measurement service: a counting fake source, a controllable clock and
the real SQLite repository on a temporary file."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.core.exceptions import UpstreamUnavailableError
from app.db.database import open_database
from app.db.repository import CacheRepository
from app.domain.freshness import CacheReport, FreshnessPolicy
from app.domain.measurements import Aggregation, MeasurementType, Observation
from app.domain.stations import Station, get_station
from app.domain.time_range import TimeRange
from app.services.measurements import MeasurementQuery, MeasurementResult, MeasurementService

STATION = get_station("juan-carlos-i")
POLICY = FreshnessPolicy(ttl=timedelta(hours=1), grace=timedelta(hours=48))
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


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
def service(
    source: CountingSource, repository: CacheRepository, clock: FakeClock
) -> MeasurementService:
    return MeasurementService(source, "aemet", repository, POLICY, clock=clock)


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
