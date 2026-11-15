"""Use case: obtain the measurements of a station for a time range, aggregated as requested."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from typing import Literal

from app.core.clock import Clock, utc_now
from app.core.exceptions import UpstreamCoolingDownError, UpstreamError
from app.db.repository import CacheRepository
from app.domain.aggregation import SeriesRow, build_series
from app.domain.chunks import CachedChunk, MonthChunk, month_chunks
from app.domain.freshness import CacheReport, FreshnessPolicy, MonthState, needs_fetch, summarize
from app.domain.measurements import Aggregation, MeasurementType
from app.domain.sources import AvailableRange, KnowsAvailableRange, WeatherSource
from app.domain.stations import Station
from app.domain.time_range import TimeRange
from app.services.circuit import DEFAULT_COOLDOWN, CircuitBreaker
from app.services.coalescing import SingleFlight

logger = logging.getLogger(__name__)

SourceLabel = Literal["aemet", "demo"]

MonthKey = tuple[str, str]
"""Station identifier and month (``"YYYY-MM"``): the unit of work that fetches are grouped by."""


@dataclass(frozen=True, slots=True)
class MeasurementQuery:
    """A validated request: every field is already a domain object."""

    station: Station
    time_range: TimeRange
    aggregation: Aggregation
    types: tuple[MeasurementType, ...]


@dataclass(frozen=True, slots=True)
class MeasurementResult:
    query: MeasurementQuery
    rows: list[SeriesRow]
    source: SourceLabel
    """Where the data came from, reported in the response metadata."""
    cache: CacheReport
    """Whether the data was served from the cache and how recent it is."""
    observation_count: int
    """Observations in the range, before aggregation."""
    available_range: AvailableRange | None = None
    """Only when the source returned nothing and knows which data it holds (demo mode)."""


class MeasurementService:
    """Serves observations from the cache, fetching from the weather source only what is missing.

    Data is fetched and cached by calendar month in UTC. Each request:

    1. splits its range into months and skips those that start in the future;
    2. fetches the months that are missing or expired (see ``app.domain.freshness``) and stores
       them, replacing any older copy; concurrent requests for the same month share one fetch;
    3. reads the whole range from the cache and aggregates it.

    When a fetch fails, an expired month that has a cached copy is served stale, and the source
    is not called again for a cool-down period (circuit breaker). A month without a copy makes
    the request fail.
    """

    def __init__(
        self,
        source: WeatherSource,
        source_label: SourceLabel,
        repository: CacheRepository,
        policy: FreshnessPolicy,
        clock: Clock = utc_now,
        flights: SingleFlight[MonthKey, tuple[CachedChunk, bool]] | None = None,
        cooldown: timedelta = DEFAULT_COOLDOWN,
    ) -> None:
        self._source = source
        self._source_label = source_label
        self._repository = repository
        self._policy = policy
        self._clock = clock
        self._flights = flights if flights is not None else SingleFlight()
        self._breaker = CircuitBreaker(cooldown, clock)

    @property
    def source_label(self) -> SourceLabel:
        return self._source_label

    def get(self, query: MeasurementQuery) -> MeasurementResult:
        # One instant per request: every month is judged against it, and it is stored as the
        # fetch time. It precedes the fetch, so the data is at least as recent as that instant.
        now = self._clock().replace(microsecond=0)
        station, time_range = query.station, query.time_range
        report = self._refresh(station, time_range, now)
        observations = self._repository.read_observations(
            station.id, time_range.start, time_range.end
        )
        rows = build_series(
            observations,
            aggregation=query.aggregation,
            types=query.types,
            station_timezone=station.local_timezone,
            start=time_range.start,
            end=time_range.end,
        )
        return MeasurementResult(
            query=query,
            rows=rows,
            source=self._source_label,
            cache=report,
            observation_count=len(observations),
            available_range=None if observations else self.available_range(station),
        )

    def available_range(self, station: Station) -> AvailableRange | None:
        """Span of the data the source holds for ``station``, when the source can tell."""
        if isinstance(self._source, KnowsAvailableRange):
            return self._source.available_range(station)
        return None

    def _refresh(self, station: Station, time_range: TimeRange, now: datetime) -> CacheReport:
        """Fetch and store the months of the range that are missing or expired."""
        # A month that starts in the future cannot have data yet: it is neither fetched nor stored.
        chunks = [c for c in month_chunks(time_range.start, time_range.end) if c.start <= now]
        cached = self._repository.cached_chunks(station.id, [chunk.key for chunk in chunks])
        months: list[MonthState] = []
        for chunk in chunks:
            current = cached.get(chunk.key)
            if current is not None and not needs_fetch(chunk, current, now, self._policy):
                months.append(MonthState(chunk, current, fetched_now=False))
                continue
            # Concurrent requests for the same month share one fetch and its outcome. A request
            # that waited for another one's fetch reports the month as fetched: it waited for it.
            try:
                entry, fetched = self._flights.run(
                    (station.id, chunk.key), partial(self._fetch_month, station, chunk, now)
                )
            except UpstreamError as error:
                if current is None:
                    raise
                logger.warning(
                    "Serving %s %s as cached at %s: %s",
                    station.id,
                    chunk.key,
                    current.fetched_at.isoformat(),
                    error,
                )
                months.append(MonthState(chunk, current, fetched_now=False, stale=True))
                continue
            months.append(MonthState(chunk, entry, fetched_now=fetched))
        return summarize(months, self._policy)

    def _fetch_month(
        self, station: Station, chunk: MonthChunk, now: datetime
    ) -> tuple[CachedChunk, bool]:
        """Fetch and store one month, unless another request has just stored a fresh copy.

        Returns:
            What the cache holds for the month, and whether it was fetched.
        """
        # Second check, now that this request is the only one working on the month: a fetch
        # that ended after the first check (made without coordination) has already stored it.
        current = self._repository.cached_chunks(station.id, [chunk.key]).get(chunk.key)
        if current is not None and not needs_fetch(chunk, current, now, self._policy):
            return current, False
        retry_after = self._breaker.retry_after_seconds()
        if retry_after is not None:
            raise UpstreamCoolingDownError(retry_after)
        try:
            # The month in progress is fetched up to now; nothing exists after it.
            observations = self._source.fetch(station, chunk.start, min(chunk.end, now))
        except UpstreamError:
            self._breaker.record_failure()
            raise
        self._breaker.record_success()
        self._repository.save_chunk(station.id, chunk, observations, fetched_at=now)
        logger.info(
            "Fetched %s %s from %s: %d observations.",
            station.id,
            chunk.key,
            self._source_label,
            len(observations),
        )
        return CachedChunk(chunk.key, now, len(observations)), True
