"""Conversion of domain results into response schemas and CSV (pure functions)."""

import csv
import io
from datetime import tzinfo
from typing import Any, Final

from app.api.schemas import (
    CacheInfo,
    FieldInfo,
    MeasurementRow,
    MeasurementsResponse,
    ResponseMetadata,
    StationOut,
    StationRef,
    TimeSpanOut,
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
from app.domain.sources import AvailableRange
from app.domain.stations import Station
from app.domain.timezones import OUTPUT_TIMEZONE, describe_timezone, format_output_datetime
from app.services.measurements import MeasurementResult

VALUE_DECIMALS = 2
"""Output values are rounded for readability; AEMET itself publishes one decimal."""

CSV_ENCODING: Final = "utf-8-sig"
"""UTF-8 with a byte order mark, so that Excel on Windows shows the degree sign correctly."""


def present_station(station: Station, available: AvailableRange | None = None) -> StationOut:
    return StationOut(
        id=station.id,
        name=station.name,
        aemet_id=station.aemet_id,
        aemet_name=station.aemet_name,
        latitude=station.latitude,
        longitude=station.longitude,
        altitude_m=station.altitude_m,
        timezone=timezone_name(station.local_timezone),
        available_range=_time_span(available) if available else None,
    )


def present_measurements(result: MeasurementResult) -> MeasurementsResponse:
    query = result.query
    station, time_range = query.station, query.time_range
    aggregated = query.aggregation is not Aggregation.NONE
    with_period = query.aggregation in (Aggregation.DAILY, Aggregation.MONTHLY)
    # Only fields that are set appear in the response, so ``notice`` is absent when not needed.
    notice = {} if result.observation_count else {"notice": _no_data_notice(result)}
    return MeasurementsResponse(
        metadata=ResponseMetadata(
            **notice,
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
            cache=CacheInfo(
                status=result.cache.status,
                last_updated=(
                    format_output_datetime(result.cache.last_updated)
                    if result.cache.last_updated is not None
                    else None
                ),
            ),
            count=len(result.rows),
        ),
        fields=_fields(query.types, aggregated=aggregated, with_period=with_period),
        data=[
            _row(row, station, query.types, aggregated=aggregated, with_period=with_period)
            for row in result.rows
        ],
    )


def render_csv(response: MeasurementsResponse) -> bytes:
    """Write the dataset as CSV, with the official labels as column headers.

    It is built from the JSON response itself, so both formats always contain exactly the same
    columns and values. Missing values are empty cells.
    """
    keys = list(response.fields)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([response.fields[key].label for key in keys])
    for row in response.data:
        values = row.model_dump()
        writer.writerow(["" if values[key] is None else values[key] for key in keys])
    return buffer.getvalue().encode(CSV_ENCODING)


def csv_filename(response: MeasurementsResponse) -> str:
    """E.g. ``juan-carlos-i_daily_2026-01-15_2026-01-16.csv`` (dates in Madrid time)."""
    metadata = response.metadata
    return (
        f"{metadata.station.id}_{metadata.aggregation.value}_"
        f"{metadata.start[:10]}_{metadata.end[:10]}.csv"
    )


def timezone_name(zone: tzinfo) -> str:
    """Display name of a time zone: ``UTC-03:00`` for the stations, the IANA key otherwise."""
    return zone.tzname(None) or describe_timezone(zone)


def _no_data_notice(result: MeasurementResult) -> str:
    station = result.query.station
    if result.source == "aemet":
        return (
            "AEMET has no data for this range. The Antarctic stations mostly report during the "
            "austral summer campaigns (roughly November to March)."
        )
    if result.available_range is None:
        return f"Demo mode: there is no recorded data for {station.name}."
    span = _time_span(result.available_range)
    return (
        f"Demo mode: there is no recorded data in this range. Recorded data for {station.name} "
        f"covers {span.start} to {span.end}."
    )


def _time_span(span: AvailableRange) -> TimeSpanOut:
    return TimeSpanOut(
        start=format_output_datetime(span.start), end=format_output_datetime(span.end)
    )


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
