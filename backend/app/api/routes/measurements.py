"""Main endpoint: time series of a station, optionally aggregated."""

from typing import Annotated, Any

from fastapi import APIRouter, Path, Query

from app.api.dependencies import MeasurementServiceDep, SettingsDep
from app.api.presenters import present_measurements
from app.api.schemas import ErrorResponse, MeasurementsResponse
from app.domain.measurements import Aggregation, parse_measurement_types
from app.domain.stations import get_station
from app.domain.time_range import resolve_range, validate_range_length
from app.services.measurements import MeasurementQuery

router = APIRouter(prefix="/api/v1", tags=["measurements"])

_ERRORS: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Unknown station."},
    422: {"model": ErrorResponse, "description": "Invalid parameter (format, DST, range)."},
    502: {"model": ErrorResponse, "description": "AEMET failed or answered unexpectedly."},
    503: {"model": ErrorResponse, "description": "AEMET is unreachable or rate limiting."},
    504: {"model": ErrorResponse, "description": "AEMET did not answer in time."},
}


@router.get(
    "/stations/{station_id}/measurements",
    summary="Measurements of a station for a time range",
    response_model=MeasurementsResponse,
    response_model_exclude_unset=True,
    responses=_ERRORS,
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
) -> MeasurementsResponse:
    """Return the time series of a station.

    Output datetimes are in Europe/Madrid with their offset. Daily and monthly buckets follow
    the station's local time (UTC-03:00). Aggregated rows include `samples`,
    `expected_samples` and `coverage`. Non-existent or ambiguous local times (daylight saving
    time changes) are rejected with 422.
    """
    station = get_station(station_id)
    time_range = resolve_range(start, end, tz)
    validate_range_length(time_range, aggregation, settings.max_range_days(aggregation))
    query = MeasurementQuery(
        station=station,
        time_range=time_range,
        aggregation=aggregation,
        types=parse_measurement_types(types),
    )
    return present_measurements(service.get(query))
