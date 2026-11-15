"""Tests of the cache repository on real temporary SQLite files."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.exc import IntegrityError

from app.db.database import open_database
from app.db.repository import CacheRepository
from app.db.schema import fetched_chunks, measurements
from app.domain.chunks import CachedChunk, MonthChunk, month_chunks
from app.domain.measurements import Observation

ConcurrentRunner = Callable[[int, Callable[[int], None]], list[BaseException]]

STATION = "juan-carlos-i"
FETCHED_AT = datetime(2026, 2, 3, 10, 0, tzinfo=UTC)


def _month(key: str) -> MonthChunk:
    year, month = map(int, key.split("-"))
    first_day = datetime(year, month, 1, tzinfo=UTC)
    return month_chunks(first_day, first_day)[0]


JANUARY = _month("2026-01")
FEBRUARY = _month("2026-02")


def _obs(iso: str, temperature: float | None = 1.0, pressure: float | None = None) -> Observation:
    return Observation(
        timestamp=datetime.fromisoformat(iso).astimezone(UTC),
        temperature=temperature,
        pressure=pressure,
        speed=None,
    )


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    engine = open_database(tmp_path / "cache.sqlite3", data_source="aemet")
    yield engine
    engine.dispose()


@pytest.fixture
def repository(engine: Engine) -> CacheRepository:
    return CacheRepository(engine)


def test_saved_observations_are_read_back_sorted(repository: CacheRepository) -> None:
    later = _obs("2026-01-15T10:10:00Z", temperature=None, pressure=990.5)
    earlier = _obs("2026-01-15T10:00:00Z", temperature=-1.25)
    repository.save_chunk(STATION, JANUARY, [later, earlier], FETCHED_AT)

    assert repository.read_observations(STATION, JANUARY.start, JANUARY.end) == [earlier, later]


def test_reads_include_both_ends_of_the_range_and_nothing_else(
    repository: CacheRepository,
) -> None:
    times = ["10:00", "10:10", "10:20", "10:30"]
    repository.save_chunk(
        STATION, JANUARY, [_obs(f"2026-01-15T{t}:00Z") for t in times], FETCHED_AT
    )

    found = repository.read_observations(
        STATION,
        datetime(2026, 1, 15, 10, 10, tzinfo=UTC),
        datetime(2026, 1, 15, 10, 20, tzinfo=UTC),
    )

    assert [o.timestamp.strftime("%H:%M") for o in found] == ["10:10", "10:20"]


def test_bounds_with_fractions_of_a_second_never_widen_the_range(
    repository: CacheRepository,
) -> None:
    times = ["10:00", "10:10", "10:20", "10:30"]
    repository.save_chunk(
        STATION, JANUARY, [_obs(f"2026-01-15T{t}:00Z") for t in times], FETCHED_AT
    )
    half_second = timedelta(milliseconds=500)

    found = repository.read_observations(
        STATION,
        datetime(2026, 1, 15, 10, 0, tzinfo=UTC) + half_second,
        datetime(2026, 1, 15, 10, 30, tzinfo=UTC) - half_second,
    )

    assert [o.timestamp.strftime("%H:%M") for o in found] == ["10:10", "10:20"]


def test_stations_are_kept_apart(repository: CacheRepository) -> None:
    repository.save_chunk(STATION, JANUARY, [_obs("2026-01-15T10:00:00Z", 1.0)], FETCHED_AT)
    repository.save_chunk(
        "gabriel-de-castilla", JANUARY, [_obs("2026-01-15T10:00:00Z", 2.0)], FETCHED_AT
    )

    found = repository.read_observations(STATION, JANUARY.start, JANUARY.end)

    assert [o.temperature for o in found] == [1.0]


def test_cached_chunks_reports_only_the_requested_months_that_are_cached(
    repository: CacheRepository,
) -> None:
    repository.save_chunk(STATION, JANUARY, [_obs("2026-01-15T10:00:00Z")], FETCHED_AT)

    cached = repository.cached_chunks(STATION, ["2025-12", "2026-01", "2026-02"])

    assert cached == {"2026-01": CachedChunk(key="2026-01", fetched_at=FETCHED_AT, row_count=1)}
    assert repository.cached_chunks("gabriel-de-castilla", ["2026-01"]) == {}
    assert repository.cached_chunks(STATION, []) == {}


def test_a_month_without_data_is_recorded_as_empty(repository: CacheRepository) -> None:
    repository.save_chunk(STATION, JANUARY, [], FETCHED_AT)

    assert repository.cached_chunks(STATION, ["2026-01"])["2026-01"].row_count == 0
    assert repository.read_observations(STATION, JANUARY.start, JANUARY.end) == []


def test_saving_a_month_again_replaces_it(repository: CacheRepository) -> None:
    february = _obs("2026-02-01T00:00:00Z")
    repository.save_chunk(STATION, FEBRUARY, [february], FETCHED_AT)
    repository.save_chunk(
        STATION,
        JANUARY,
        [_obs(f"2026-01-15T10:{m}:00Z") for m in ("00", "10", "20")],
        FETCHED_AT,
    )
    refetched_at = FETCHED_AT + timedelta(hours=1)
    # The source corrected 10:10 and no longer publishes 10:00 and 10:20.
    corrected = _obs("2026-01-15T10:10:00Z", temperature=5.0)
    new = _obs("2026-01-15T10:30:00Z")

    repository.save_chunk(STATION, JANUARY, [corrected, new], refetched_at)

    assert repository.read_observations(STATION, JANUARY.start, JANUARY.end) == [corrected, new]
    assert repository.cached_chunks(STATION, ["2026-01"])["2026-01"] == CachedChunk(
        key="2026-01", fetched_at=refetched_at, row_count=2
    )
    assert repository.read_observations(STATION, FEBRUARY.start, FEBRUARY.end) == [february]


def test_observations_outside_the_month_are_rejected(repository: CacheRepository) -> None:
    with pytest.raises(ValueError, match="outside 2026-01"):
        repository.save_chunk(STATION, JANUARY, [_obs("2026-02-01T00:00:00Z")], FETCHED_AT)

    assert repository.cached_chunks(STATION, ["2026-01"]) == {}


def test_a_naive_fetch_time_is_rejected(repository: CacheRepository) -> None:
    naive = datetime(2026, 2, 3, 10, 0)  # noqa: DTZ001 - naive on purpose

    with pytest.raises(ValueError, match="Naive"):
        repository.save_chunk(STATION, JANUARY, [], naive)


def test_a_failed_save_keeps_the_previous_month(repository: CacheRepository) -> None:
    previous = [_obs("2026-01-15T10:00:00Z"), _obs("2026-01-15T10:10:00Z")]
    repository.save_chunk(STATION, JANUARY, previous, FETCHED_AT)
    duplicated = _obs("2026-01-16T00:00:00Z")

    # The old rows are already deleted when the duplicated timestamp breaks the primary key.
    with pytest.raises(IntegrityError):
        repository.save_chunk(STATION, JANUARY, [duplicated, duplicated], FETCHED_AT)

    assert repository.read_observations(STATION, JANUARY.start, JANUARY.end) == previous
    assert repository.cached_chunks(STATION, ["2026-01"])["2026-01"].row_count == 2


def test_readers_never_see_a_half_written_month(
    engine: Engine, repository: CacheRepository, run_concurrently: ConcurrentRunner
) -> None:
    # Writers keep replacing January with versions of different sizes while readers check, in a
    # single read transaction, that the rows stored always match the month's row_count.
    start = datetime(2026, 1, 1, tzinfo=UTC)
    versions = [
        [_obs((start + timedelta(minutes=10 * i)).isoformat()) for i in range(size)]
        for size in (100, 250, 400, 550)
    ]
    writers, readers, rounds = len(versions), 4, 10
    mismatches: list[tuple[int, int]] = []

    def work(index: int) -> None:
        for _ in range(rounds):
            if index < writers:
                repository.save_chunk(STATION, JANUARY, versions[index], FETCHED_AT)
            else:
                with engine.connect() as connection:
                    stored = connection.execute(
                        select(func.count()).select_from(measurements)
                    ).scalar_one()
                    declared = connection.execute(
                        select(fetched_chunks.c.row_count)
                    ).scalar_one_or_none()
                if stored != (declared or 0):
                    mismatches.append((stored, declared or 0))

    errors = run_concurrently(writers + readers, work)

    assert errors == []
    assert mismatches == []
    final = repository.cached_chunks(STATION, ["2026-01"])["2026-01"].row_count
    assert final in {len(version) for version in versions}
    assert len(repository.read_observations(STATION, JANUARY.start, JANUARY.end)) == final


def test_range_reads_use_the_primary_key(engine: Engine) -> None:
    # Same shape as the repository's query: one station, a timestamp range, sorted by time.
    query = (
        "EXPLAIN QUERY PLAN SELECT ts_utc, temperature FROM measurements "
        "WHERE station_id = 'juan-carlos-i' AND ts_utc BETWEEN 0 AND 100 ORDER BY ts_utc"
    )
    with engine.connect() as connection:
        plan = " ".join(row[-1] for row in connection.exec_driver_sql(query))

    assert "USING PRIMARY KEY" in plan
    assert "TEMP B-TREE" not in plan  # rows already come in order: no sort step
