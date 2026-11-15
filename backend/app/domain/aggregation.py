"""Time aggregation of observations: pure functions built on pandas.

Hourly, daily and monthly buckets follow the station's local time. Every row carries its
timestamp as an aware UTC instant; the API layer writes it in Europe/Madrid.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Final

import pandas as pd

from app.domain.measurements import Aggregation, MeasurementType, Observation

SAMPLE_INTERVAL: Final = timedelta(minutes=10)
"""Upstream granularity: one observation every ten minutes."""

_FREQUENCIES: Final = {
    Aggregation.HOURLY: "h",
    Aggregation.DAILY: "D",
    Aggregation.MONTHLY: "MS",  # month start
}
_PERIOD_FORMATS: Final = {Aggregation.DAILY: "%Y-%m-%d", Aggregation.MONTHLY: "%Y-%m"}


@dataclass(frozen=True, slots=True)
class SeriesRow:
    """One row of the output dataset: a raw observation or an aggregated bucket."""

    timestamp: datetime
    """Aware UTC instant: the observation time, or the start of the bucket."""
    values: Mapping[MeasurementType, float | None] = field(default_factory=dict)
    """Values of the requested measurement types only (means for aggregated rows)."""
    period: str | None = None
    """Station-local day (``2026-03-29``) or month (``2026-03``) of daily and monthly rows."""
    samples: int | None = None
    """Aggregated rows: observations with at least one requested value in the bucket."""
    expected_samples: int | None = None
    """Aggregated rows: ten-minute slots in a complete bucket (6, 144, or days x 144)."""
    coverage: float | None = None
    """Aggregated rows: ``samples / expected_samples`` as a percentage, rounded to 0.1."""


def build_series(
    observations: Sequence[Observation],
    *,
    aggregation: Aggregation,
    types: Sequence[MeasurementType],
    station_timezone: tzinfo,
    start: datetime,
    end: datetime,
) -> list[SeriesRow]:
    """Turn observations into the output rows for the requested aggregation level.

    Only observations with at least one value among ``types`` are used. Without aggregation they
    are returned as they are. Otherwise they are grouped into buckets of the station's local time:
    each value is the mean of its non-missing observations, and every bucket between ``start``
    and ``end`` is returned, including empty ones (``samples == 0``), so gaps stay visible.
    """
    relevant = [obs for obs in observations if any(obs.value(kind) is not None for kind in types)]
    if aggregation is Aggregation.NONE:
        return [
            SeriesRow(timestamp=obs.timestamp, values={kind: obs.value(kind) for kind in types})
            for obs in relevant
        ]
    return _aggregate(relevant, aggregation, types, station_timezone, start, end)


def _aggregate(
    observations: Sequence[Observation],
    aggregation: Aggregation,
    types: Sequence[MeasurementType],
    station_timezone: tzinfo,
    start: datetime,
    end: datetime,
) -> list[SeriesRow]:
    frame = pd.DataFrame(
        {kind.value: [obs.value(kind) for obs in observations] for kind in types},
        index=pd.to_datetime([obs.timestamp for obs in observations], utc=True),
        dtype="float64",
    ).tz_convert(station_timezone)

    frequency = _FREQUENCIES[aggregation]
    first = _bucket_start(start, aggregation, station_timezone)
    buckets = pd.date_range(
        start=first, end=_bucket_start(end, aggregation, station_timezone), freq=frequency
    )
    # Bucket i spans [edges[i], edges[i + 1]): its real length gives the expected sample count,
    # which stays correct for months of any length (and for 23/25-hour days in zones with DST).
    edges = pd.date_range(start=first, periods=len(buckets) + 1, freq=frequency)
    expected = (edges[1:] - edges[:-1]) // SAMPLE_INTERVAL

    resampled = frame.resample(frequency)
    means = resampled.mean().reindex(buckets)
    samples = resampled.size().reindex(buckets, fill_value=0).to_numpy()
    columns = {kind: means[kind.value].to_numpy() for kind in types}
    starts = buckets.tz_convert(UTC).to_pydatetime()
    period_format = _PERIOD_FORMATS.get(aggregation)
    periods = list(buckets.strftime(period_format)) if period_format else [None] * len(buckets)

    rows: list[SeriesRow] = []
    for position, bucket_start in enumerate(starts):
        count, slots = int(samples[position]), int(expected[position])
        rows.append(
            SeriesRow(
                timestamp=bucket_start,
                values={kind: _optional_float(columns[kind][position]) for kind in types},
                period=periods[position],
                samples=count,
                expected_samples=slots,
                coverage=round(100 * count / slots, 1),
            )
        )
    return rows


def _bucket_start(instant: datetime, aggregation: Aggregation, zone: tzinfo) -> pd.Timestamp:
    """Start of the station-local bucket that contains ``instant``."""
    local = pd.Timestamp(instant).tz_convert(zone)
    if aggregation is Aggregation.HOURLY:
        return local.floor("h")
    day = local.normalize()
    return day if aggregation is Aggregation.DAILY else day.replace(day=1)


def _optional_float(value: object) -> float | None:
    """Convert a numpy/pandas cell to a float, turning NaN (no data) into ``None``."""
    if isinstance(value, int | float) and not math.isnan(value):
        return float(value)
    return None
