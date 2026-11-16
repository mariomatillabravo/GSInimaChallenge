"""Main endpoint: time series of a station, optionally aggregated."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query, Response

from app.api.dependencies import MeasurementServiceDep, SettingsDep
from app.api.presenters import csv_filename, present_measurements, render_csv
from app.api.schemas import ErrorResponse, MeasurementsResponse, OutputFormat
from app.domain.measurements import Aggregation, parse_measurement_types
from app.domain.stations import get_station
from app.domain.time_range import resolve_range, validate_range_length
from app.domain.wind import MetricSet, select_metrics
from app.services.measurements import MeasurementQuery

router = APIRouter(prefix="/api/v1", tags=["measurements"])

CACHE_STATUS_HEADER = "X-Cache-Status"
"""Repeats ``metadata.cache.status``, so CSV downloads (which have no metadata) carry it too."""
DATA_STALE_HEADER = "X-Data-Stale"
"""Repeats ``metadata.cache.stale`` as ``true`` or ``false``, for the same reason."""

_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "JSON by default; CSV with the official column labels when `format=csv`.",
        "content": {"text/csv": {"schema": {"type": "string"}}},
        "headers": {
            CACHE_STATUS_HEADER: {
                "description": "`hit`, `miss` or `partial`, as in `metadata.cache.status`.",
                "schema": {"type": "string"},
            },
            DATA_STALE_HEADER: {
                "description": "`true` or `false`, as in `metadata.cache.stale`.",
                "schema": {"type": "string"},
            },
        },
    },
    404: {"model": ErrorResponse, "description": "Unknown station."},
    422: {"model": ErrorResponse, "description": "Invalid parameter (format, DST, range)."},
    502: {"model": ErrorResponse, "description": "AEMET failed or answered unexpectedly."},
    503: {
        "model": ErrorResponse,
        "description": (
            "AEMET is unreachable or rate limiting, and a month of the range has no cached copy. "
            "Right after a failure AEMET is not called for a while; `Retry-After` then says when "
            "to try again."
        ),
    },
    504: {"model": ErrorResponse, "description": "AEMET did not answer in time."},
}


@router.get(
    "/stations/{station_id}/measurements",
    summary="Measurements of a station for a time range",
    response_model=MeasurementsResponse,
    response_model_exclude_unset=True,
    responses=_RESPONSES,
)
def get_measurements(
    station_id: Annotated[str, Path(description="Station identifier.", examples=["juan-carlos-i"])],
    start: Annotated[
        str,
        Query(
            description=(
                "Start of the range, inclusive: `YYYY-MM-DDTHH:MM:SS`, optionally followed by "
                "`Z` or an offset such as `+02:00` (written `%2B02:00` in a URL)."
            ),
            examples=["2025-03-29T00:00:00"],
        ),
    ],
    end: Annotated[
        str,
        Query(
            description="End of the range, inclusive. Same format as `start`.",
            examples=["2025-03-31T00:00:00"],
        ),
    ],
    service: MeasurementServiceDep,
    settings: SettingsDep,
    response: Response,
    tz: Annotated[
        str | None,
        Query(
            description=(
                "Time zone of `start` and `end` when they have no offset: an IANA name "
                "(`Europe/Berlin`) or an offset (`+02:00`). Default: `Europe/Madrid`."
            ),
            examples=["Europe/Berlin"],
        ),
    ] = None,
    aggregation: Annotated[
        Aggregation,
        Query(description="`none` returns the ten-minute observations; otherwise, means."),
    ] = Aggregation.NONE,
    types: Annotated[
        list[str] | None,
        Query(
            description=(
                "Measurement types to return: `temperature`, `pressure`, `speed`. "
                "Comma-separated or repeated. Empty: all of them."
            ),
        ),
    ] = None,
    metrics: Annotated[
        MetricSet | None,
        Query(
            description=(
                "`extended` adds wind-energy metrics to aggregated rows: cubic mean and maximum "
                "speed, temperature extremes, air density and wind power density. Each one appears "
                "when the measurement types it needs are requested."
            ),
        ),
    ] = None,
    output_format: Annotated[
        OutputFormat,
        Query(
            alias="format",
            description="`json` (default) or `csv`, a download with the official column labels.",
        ),
    ] = OutputFormat.JSON,
) -> MeasurementsResponse | Response:
    """Return the time series of a station.

    Output datetimes are in Europe/Madrid with their offset. Daily and monthly buckets follow
    the station's local time (UTC-03:00). Aggregated rows include `samples`,
    `expected_samples` and `coverage`. Non-existent or ambiguous local times (daylight saving
    time changes) are rejected with 422.
    """
    station = get_station(station_id)
    time_range = resolve_range(start, end, tz)
    validate_range_length(time_range, aggregation, settings.max_range_days(aggregation))
    measurement_types = parse_measurement_types(types)
    query = MeasurementQuery(
        station=station,
        time_range=time_range,
        aggregation=aggregation,
        types=measurement_types,
        metrics=select_metrics(metrics, aggregation, measurement_types),
    )
    body = present_measurements(service.get(query))
    cache_header = {
        CACHE_STATUS_HEADER: body.metadata.cache.status,
        DATA_STALE_HEADER: "true" if body.metadata.cache.stale else "false",
    }
    if output_format is OutputFormat.CSV:
        return Response(
            content=render_csv(body),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{csv_filename(body)}"',
                **cache_header,
            },
        )
    response.headers.update(cache_header)
    return body
