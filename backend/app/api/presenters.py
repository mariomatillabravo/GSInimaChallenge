"""Conversion of domain results into response schemas (pure functions)."""

from datetime import tzinfo
from typing import Any

from app.api.schemas import (
    FieldInfo,
    MeasurementRow,
    MeasurementsResponse,
    ResponseMetadata,
    StationOut,
    StationRef,
)
from app.domain.aggregation import SeriesRow
from app.domain.measurements import (
    COVERAGE_LABEL,
    DATETIME_LABEL,
    EXPECTED_SAMPLES_LABEL,
    MEASUREMENT_FIELDS,
    PERIOD_LABEL,
    SAMPLES_LABEL,
    STATION_LABEL,
    Aggregation,
    MeasurementType,
)
from app.domain.stations import Station
from app.domain.timezones import OUTPUT_TIMEZONE, describe_timezone, format_output_datetime
from app.services.measurements import MeasurementResult

VALUE_DECIMALS = 2
"""Output values are rounded for readability; AEMET itself publishes one decimal."""


def present_station(station: Station) -> StationOut:
    return StationOut(
        id=station.id,
        name=station.name,
        aemet_id=station.aemet_id,
        aemet_name=station.aemet_name,
        latitude=station.latitude,
        longitude=station.longitude,
        altitude_m=station.altitude_m,
        timezone=timezone_name(station.local_timezone),
    )


def present_measurements(result: MeasurementResult) -> MeasurementsResponse:
    query = result.query
    station, time_range = query.station, query.time_range
    aggregated = query.aggregation is not Aggregation.NONE
    with_period = query.aggregation in (Aggregation.DAILY, Aggregation.MONTHLY)
    return MeasurementsResponse(
        metadata=ResponseMetadata(
            station=StationRef(
                id=station.id,
                name=station.name,
                aemet_id=station.aemet_id,
                aemet_name=station.aemet_name,
            ),
            aggregation=query.aggregation,
            start=format_output_datetime(time_range.start),
            end=format_output_datetime(time_range.end),
            input_interpretation=time_range.input_interpretation,
            output_timezone=OUTPUT_TIMEZONE.key,
            station_timezone=timezone_name(station.local_timezone),
            source=result.source,
            count=len(result.rows),
        ),
        fields=_fields(query.types, aggregated=aggregated, with_period=with_period),
        data=[
            _row(row, station, query.types, aggregated=aggregated, with_period=with_period)
            for row in result.rows
        ],
    )


def timezone_name(zone: tzinfo) -> str:
    """Display name of a time zone: ``UTC-03:00`` for the stations, the IANA key otherwise."""
    return zone.tzname(None) or describe_timezone(zone)


def _row(
    row: SeriesRow,
    station: Station,
    types: tuple[MeasurementType, ...],
    *,
    aggregated: bool,
    with_period: bool,
) -> MeasurementRow:
    # Only keys that are set appear in the response (``exclude_unset``), so unrequested
    # measurements are absent while missing values are explicit nulls.
    values: dict[str, Any] = {
        "station": station.name,
        "datetime": format_output_datetime(row.timestamp),
    }
    if with_period:
        values["period"] = row.period
    for kind in types:
        values[MEASUREMENT_FIELDS[kind].key] = _round(row.values[kind])
    if aggregated:
        values |= {
            "samples": row.samples,
            "expected_samples": row.expected_samples,
            "coverage": row.coverage,
        }
    return MeasurementRow.model_validate(values)


def _fields(
    types: tuple[MeasurementType, ...], *, aggregated: bool, with_period: bool
) -> dict[str, FieldInfo]:
    # ``unit`` is always set explicitly (null when there is none) so every entry has the same shape.
    fields = {
        "station": FieldInfo(label=STATION_LABEL, unit=None),
        "datetime": FieldInfo(label=DATETIME_LABEL, unit=None),
    }
    if with_period:
        fields["period"] = FieldInfo(label=PERIOD_LABEL, unit=None)
    for kind in types:
        spec = MEASUREMENT_FIELDS[kind]
        fields[spec.key] = FieldInfo(label=spec.label, unit=spec.unit)
    if aggregated:
        fields["samples"] = FieldInfo(label=SAMPLES_LABEL, unit=None)
        fields["expected_samples"] = FieldInfo(label=EXPECTED_SAMPLES_LABEL, unit=None)
        fields["coverage"] = FieldInfo(label=COVERAGE_LABEL, unit="%")
    return fields


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, VALUE_DECIMALS)
