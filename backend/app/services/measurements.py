"""Use case: obtain the measurements of a station for a time range, aggregated as requested."""

from dataclasses import dataclass
from typing import Literal

from app.domain.aggregation import SeriesRow, build_series
from app.domain.measurements import Aggregation, MeasurementType
from app.domain.sources import AvailableRange, KnowsAvailableRange, WeatherSource
from app.domain.stations import Station
from app.domain.time_range import TimeRange

SourceLabel = Literal["aemet", "demo"]


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
    observation_count: int
    """Observations returned by the source, before aggregation."""
    available_range: AvailableRange | None = None
    """Only when the source returned nothing and knows which data it holds (demo mode)."""


class MeasurementService:
    """Fetches observations from a weather source and turns them into output rows."""

    def __init__(self, source: WeatherSource, source_label: SourceLabel) -> None:
        self._source = source
        self._source_label = source_label

    @property
    def source_label(self) -> SourceLabel:
        return self._source_label

    def get(self, query: MeasurementQuery) -> MeasurementResult:
        time_range = query.time_range
        observations = self._source.fetch(query.station, time_range.start, time_range.end)
        rows = build_series(
            observations,
            aggregation=query.aggregation,
            types=query.types,
            station_timezone=query.station.local_timezone,
            start=time_range.start,
            end=time_range.end,
        )
        return MeasurementResult(
            query=query,
            rows=rows,
            source=self._source_label,
            observation_count=len(observations),
            available_range=None if observations else self.available_range(query.station),
        )

    def available_range(self, station: Station) -> AvailableRange | None:
        """Span of the data the source holds for ``station``, when the source can tell."""
        if isinstance(self._source, KnowsAvailableRange):
            return self._source.available_range(station)
        return None
