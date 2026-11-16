"""Wind-energy metrics computed per aggregation bucket (synthetic observations)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.aggregation import SeriesRow, build_series
from app.domain.measurements import Aggregation, MeasurementType, Observation
from app.domain.stations import ANTARCTIC_STATION_TIME
from app.domain.wind import WindMetric, air_density

ALL_TYPES = tuple(MeasurementType)
NOON = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)  # 09:00 at the station: an hourly bucket start


def at(
    minutes: int, temperature: float | None, pressure: float | None, speed: float | None
) -> Observation:
    return Observation(NOON + timedelta(minutes=minutes), temperature, pressure, speed)


def hourly(
    observations: Sequence[Observation],
    hours: int = 1,
    metrics: Sequence[WindMetric] = tuple(WindMetric),
    types: Sequence[MeasurementType] = ALL_TYPES,
) -> list[SeriesRow]:
    return build_series(
        observations,
        aggregation=Aggregation.HOURLY,
        types=types,
        station_timezone=ANTARCTIC_STATION_TIME,
        start=NOON,
        end=NOON + timedelta(hours=hours) - timedelta(minutes=10),
        metrics=metrics,
    )


def test_power_density_is_the_mean_of_each_observations_power() -> None:
    [row] = hourly([at(0, 0.0, 1000.0, 0.0), at(10, 0.0, 1000.0, 10.0)])

    density = air_density(1000.0, 0.0)
    # Mean of ½·rho·0³ and ½·rho·10³; ½·rho·5³ (from the mean speed) would be four times lower.
    assert row.metrics[WindMetric.POWER_DENSITY] == pytest.approx(0.5 * density * 1000 / 2)
    assert row.metrics[WindMetric.SPEED_CUBIC_MEAN] == pytest.approx(500 ** (1 / 3))
    assert row.values[MeasurementType.SPEED] == pytest.approx(5.0)


def test_extremes_and_density_come_from_the_ten_minute_values() -> None:
    [row] = hourly(
        [at(0, -2.0, 990.0, 3.0), at(10, 1.0, 990.0, 7.5), at(20, 0.5, 1000.0, 4.0)],
    )

    assert row.metrics[WindMetric.SPEED_MAX] == 7.5
    assert row.metrics[WindMetric.TEMPERATURE_MIN] == -2.0
    assert row.metrics[WindMetric.TEMPERATURE_MAX] == 1.0
    expected_density = (
        air_density(990.0, -2.0) + air_density(990.0, 1.0) + air_density(1000.0, 0.5)
    ) / 3
    assert row.metrics[WindMetric.AIR_DENSITY] == pytest.approx(expected_density)


def test_each_metric_uses_only_the_observations_that_have_its_inputs() -> None:
    [row] = hourly([at(0, 0.0, 1000.0, 10.0), at(10, None, 1000.0, 2.0)])

    # Density and power need temperature: only the first observation counts for them.
    assert row.metrics[WindMetric.AIR_DENSITY] == pytest.approx(air_density(1000.0, 0.0))
    assert row.metrics[WindMetric.POWER_DENSITY] == pytest.approx(
        0.5 * air_density(1000.0, 0.0) * 1000
    )
    # Speed statistics use both.
    assert row.metrics[WindMetric.SPEED_MAX] == 10.0
    assert row.metrics[WindMetric.SPEED_CUBIC_MEAN] == pytest.approx(((1000 + 8) / 2) ** (1 / 3))


def test_an_empty_bucket_has_no_metrics() -> None:
    rows = hourly([at(0, 0.0, 1000.0, 5.0)], hours=2)

    assert rows[1].samples == 0
    assert set(rows[1].metrics.values()) == {None}
    assert set(rows[1].metrics) == set(WindMetric)


def test_without_metrics_the_rows_carry_none() -> None:
    [row] = hourly([at(0, 0.0, 1000.0, 5.0)], metrics=())

    assert row.metrics == {}


def test_only_the_requested_metrics_are_computed() -> None:
    [row] = hourly(
        [at(0, 0.0, 1000.0, 5.0)],
        metrics=(WindMetric.SPEED_MAX,),
        types=(MeasurementType.SPEED,),
    )

    assert row.metrics == {WindMetric.SPEED_MAX: 5.0}
