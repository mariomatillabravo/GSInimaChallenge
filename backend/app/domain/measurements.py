"""Measurement types, aggregation levels and how measurements are named for clients."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final


class Aggregation(StrEnum):
    """Time aggregation requested by the client. ``NONE`` returns the raw 10-minute records."""

    NONE = "none"
    HOURLY = "hourly"
    DAILY = "daily"
    MONTHLY = "monthly"


class MeasurementType(StrEnum):
    """Measurements exposed by the API."""

    TEMPERATURE = "temperature"
    PRESSURE = "pressure"
    SPEED = "speed"


@dataclass(frozen=True, slots=True)
class MeasurementField:
    """How a measurement is read from AEMET and presented to clients."""

    aemet_name: str
    """Field name in AEMET records."""
    key: str
    """snake_case key used in JSON responses."""
    label: str
    """Official dataset field name, used in CSV headers and in the user interface."""
    unit: str


# The challenge statement (copying AEMET's own metadata) writes "ºC" (ordinal indicator, U+00BA)
# and "hpa". The correct symbols are the degree sign (U+00B0) and "hPa".
MEASUREMENT_FIELDS: Final[MappingProxyType[MeasurementType, MeasurementField]] = MappingProxyType(
    {
        MeasurementType.TEMPERATURE: MeasurementField(
            aemet_name="temp", key="temperature_c", label="Temperature (°C)", unit="°C"
        ),
        MeasurementType.PRESSURE: MeasurementField(
            aemet_name="pres", key="pressure_hpa", label="Pressure (hPa)", unit="hPa"
        ),
        MeasurementType.SPEED: MeasurementField(
            aemet_name="vel", key="speed_ms", label="Speed (m/s)", unit="m/s"
        ),
    }
)

STATION_LABEL: Final = "Station"
DATETIME_LABEL: Final = "Datetime"


@dataclass(frozen=True, slots=True)
class Observation:
    """One cleaned 10-minute observation of a station.

    A value is ``None`` when it is missing upstream or flagged as bad quality. An observation
    always has at least one value; records without any usable value are discarded when parsing.
    """

    timestamp: datetime
    """Timezone-aware, in UTC."""
    temperature: float | None
    pressure: float | None
    speed: float | None

    def value(self, kind: MeasurementType) -> float | None:
        """Return the value of the given measurement type."""
        return {
            MeasurementType.TEMPERATURE: self.temperature,
            MeasurementType.PRESSURE: self.pressure,
            MeasurementType.SPEED: self.speed,
        }[kind]
