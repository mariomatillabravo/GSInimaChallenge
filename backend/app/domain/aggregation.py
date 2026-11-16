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
from pandas.core.resample import Resampler

from app.domain.measurements import Aggregation, MeasurementType, Observation
from app.domain.wind import WindMetric, air_density, cubic_mean, power_density

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
    metrics: Mapping[WindMetric, float | None] = field(default_factory=dict)
    """Aggregated rows with ``metrics=extended``: the requested wind-energy metrics."""


def build_series(
    observations: Sequence[Observation],
    *,
    aggregation: Aggregation,
    types: Sequence[MeasurementType],
    station_timezone: tzinfo,
    start: datetime,
    end: datetime,
    metrics: Sequence[WindMetric] = (),
) -> list[SeriesRow]:
    """Turn observations into the output rows for the requested aggregation level.

    Only observations with at least one value among ``types`` are used. Without aggregation they
    are returned as they are. Otherwise they are grouped into buckets of the station's local time:
    each value is the mean of its non-missing observations, and every bucket between ``start``
    and ``end`` is returned, including empty ones (``samples == 0``), so gaps stay visible.
    ``metrics`` (aggregated levels only) adds wind-energy statistics to each bucket.
    """
    relevant = [obs for obs in observations if any(obs.value(kind) is not None for kind in types)]
    if aggregation is Aggregation.NONE:
        return [
            SeriesRow(timestamp=obs.timestamp, values={kind: obs.value(kind) for kind in types})
            for obs in relevant
        ]
    return _aggregate(relevant, aggregation, types, station_timezone, start, end, metrics)


def _aggregate(
    observations: Sequence[Observation],
    aggregation: Aggregation,
    types: Sequence[MeasurementType],
    station_timezone: tzinfo,
    start: datetime,
    end: datetime,
    metrics: Sequence[WindMetric],
) -> list[SeriesRow]:
    columns_in: dict[str, list[float | None]] = {
        kind.value: [obs.value(kind) for obs in observations] for kind in types
    }
    if WindMetric.AIR_DENSITY in metrics or WindMetric.POWER_DENSITY in metrics:
        columns_in |= _air_columns(observations)
    frame = pd.DataFrame(
        columns_in,
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
    metric_columns = {
        metric: _metric_by_bucket(resampled, metric).reindex(buckets).to_numpy()
        for metric in metrics
    }
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
                metrics={
                    metric: _optional_float(metric_columns[metric][position]) for metric in metrics
                },
            )
        )
    return rows


_AIR_DENSITY: Final = "air_density"
_POWER_DENSITY: Final = "power_density"


def _air_columns(observations: Sequence[Observation]) -> dict[str, list[float | None]]:
    """Air density and power density of each observation that has the values they need.

    They are computed per observation, before averaging: the power of one bucket is the mean of
    each observation's ½·rho·v³, not ½·rho·v³ of the mean speed, which would underestimate it.
    """
    densities: list[float | None] = []
    powers: list[float | None] = []
    for obs in observations:
        density = (
            air_density(obs.pressure, obs.temperature)
            if obs.pressure is not None and obs.temperature is not None
            else None
        )
        densities.append(density)
        powers.append(
            power_density(density, obs.speed)
            if density is not None and obs.speed is not None
            else None
        )
    return {_AIR_DENSITY: densities, _POWER_DENSITY: powers}


def _metric_by_bucket(resampled: "Resampler[pd.DataFrame]", metric: WindMetric) -> pd.Series:
    """One value of ``metric`` per bucket that has observations (empty buckets get none).

    The annotation is quoted: ``Resampler`` is generic only in the type stubs, not at run time.
    """
    speed, temperature = MeasurementType.SPEED.value, MeasurementType.TEMPERATURE.value
    match metric:
        case WindMetric.SPEED_CUBIC_MEAN:
            return resampled[speed].apply(lambda speeds: cubic_mean(speeds.dropna()))
        case WindMetric.SPEED_MAX:
            return resampled[speed].max()
        case WindMetric.TEMPERATURE_MIN:
            return resampled[temperature].min()
        case WindMetric.TEMPERATURE_MAX:
            return resampled[temperature].max()
        case WindMetric.AIR_DENSITY:
            return resampled[_AIR_DENSITY].mean()
        case WindMetric.POWER_DENSITY:
            return resampled[_POWER_DENSITY].mean()


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
