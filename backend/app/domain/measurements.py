"""Measurement types, aggregation levels and how measurements are named for clients."""

from dataclasses import dataclass
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
