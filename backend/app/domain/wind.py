"""Wind-energy metrics: their definitions and formulas (pure functions).

These are statistics of an aggregation bucket, returned with ``metrics=extended``. Speeds are
measured by the station at about 10 m, far below a turbine's hub (80 to 120 m): the metrics
describe the site at sensor height, without extrapolating them.
"""

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.core.exceptions import InvalidParameterError
from app.domain.measurements import Aggregation, MeasurementType

DRY_AIR_GAS_CONSTANT: Final = 287.05
"""Specific gas constant of dry air, in J/(kg·K)."""
CELSIUS_TO_KELVIN: Final = 273.15
PASCALS_PER_HECTOPASCAL: Final = 100.0


class MetricSet(StrEnum):
    """Values of the ``metrics`` parameter."""

    EXTENDED = "extended"


class WindMetric(StrEnum):
    """Metrics returned with ``metrics=extended``."""

    SPEED_CUBIC_MEAN = "speed_cubic_mean"
    SPEED_MAX = "speed_max"
    TEMPERATURE_MIN = "temperature_min"
    TEMPERATURE_MAX = "temperature_max"
    AIR_DENSITY = "air_density"
    POWER_DENSITY = "power_density"


@dataclass(frozen=True, slots=True)
class MetricField:
    """How a metric is named for clients and which measurements it is computed from."""

    key: str
    """snake_case key used in JSON responses."""
    label: str
    """Label used in CSV headers and in the user interface."""
    unit: str
    decimals: int
    """Rounding in responses: air density is about 1.3 kg/m³, so it needs three decimals."""
    inputs: frozenset[MeasurementType]
    """Measurement types the metric needs; it is returned only when all of them are requested."""


_SPEED = frozenset({MeasurementType.SPEED})
_TEMPERATURE = frozenset({MeasurementType.TEMPERATURE})
_AIR = frozenset({MeasurementType.TEMPERATURE, MeasurementType.PRESSURE})
_ALL = frozenset(MeasurementType)

# Maximum speed and the temperature extremes come from the stored ten-minute means, so the
# labels say so: AEMET's in-interval maxima and minima (gusts) are not stored by the cache.
METRIC_FIELDS: Final[MappingProxyType[WindMetric, MetricField]] = MappingProxyType(
    {
        WindMetric.SPEED_CUBIC_MEAN: MetricField(
            "speed_cubic_mean_ms", "Cubic mean speed (m/s)", "m/s", 2, _SPEED
        ),
        WindMetric.SPEED_MAX: MetricField(
            "speed_max_ms", "Maximum 10-minute speed (m/s)", "m/s", 2, _SPEED
        ),
        WindMetric.TEMPERATURE_MIN: MetricField(
            "temperature_min_c", "Minimum 10-minute temperature (°C)", "°C", 2, _TEMPERATURE
        ),
        WindMetric.TEMPERATURE_MAX: MetricField(
            "temperature_max_c", "Maximum 10-minute temperature (°C)", "°C", 2, _TEMPERATURE
        ),
        WindMetric.AIR_DENSITY: MetricField(
            "air_density_kgm3", "Air density (kg/m³)", "kg/m³", 3, _AIR
        ),
        WindMetric.POWER_DENSITY: MetricField(
            "power_density_wm2", "Wind power density (W/m²)", "W/m²", 1, _ALL
        ),
    }
)


def select_metrics(
    option: MetricSet | None,
    aggregation: Aggregation,
    types: Iterable[MeasurementType],
) -> tuple[WindMetric, ...]:
    """The metrics a request gets: those whose inputs are all among the requested types.

    Raises:
        InvalidParameterError: If metrics are asked for raw ten-minute records, where a bucket
            statistic would just repeat each value.
    """
    if option is None:
        return ()
    if aggregation is Aggregation.NONE:
        raise InvalidParameterError(
            "metrics",
            "Wind-energy metrics are statistics of a bucket: choose an aggregation level "
            "(hourly, daily or monthly).",
        )
    requested = frozenset(types)
    return tuple(metric for metric in WindMetric if METRIC_FIELDS[metric].inputs <= requested)


def air_density(pressure_hpa: float, temperature_c: float) -> float:
    """Density of dry air in kg/m³: rho = p / (R·T), with p in pascals and T in kelvins.

    Humidity is ignored: even saturated air at 0 °C and 980 hPa is only about 0.24 % lighter
    (vapour pressure 6.11 hPa; rho_moist / rho_dry ≈ 1 - 0.378·e/p), and Antarctic air is drier.
    """
    return (pressure_hpa * PASCALS_PER_HECTOPASCAL) / (
        DRY_AIR_GAS_CONSTANT * (temperature_c + CELSIUS_TO_KELVIN)
    )


def power_density(air_density_kgm3: float, speed_ms: float) -> float:
    """Power of the wind through one square metre, in W/m²: ½·rho·v³."""
    return 0.5 * air_density_kgm3 * speed_ms**3


def cubic_mean(speeds: Iterable[float]) -> float | None:
    """∛(mean of v³): the constant speed that carries the same energy as the measured ones.

    The power of the wind grows with the cube of its speed, so the plain mean underestimates
    it: speeds of 0 and 10 m/s average 5 m/s, but carry as much energy as about 7.94 m/s.
    ``None`` when there are no speeds.
    """
    values = list(speeds)
    if not values:
        return None
    return math.cbrt(sum(speed**3 for speed in values) / len(values))
