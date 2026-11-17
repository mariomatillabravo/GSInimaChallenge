"""Response schemas: the public contract of the API, also used to generate the OpenAPI document."""

from typing import Literal

from pydantic import BaseModel, Field

from app.domain.enums import CaseInsensitiveStrEnum
from app.domain.measurements import Aggregation, MeasurementType
from app.domain.wind import WindMetric


class OutputFormat(CaseInsensitiveStrEnum):
    JSON = "json"
    CSV = "csv"


class TimeSpanOut(BaseModel):
    start: str = Field(examples=["2025-03-01T01:00:00+01:00"])
    end: str = Field(examples=["2025-04-01T01:50:00+02:00"])


class StationOut(BaseModel):
    id: str = Field(examples=["juan-carlos-i"], description="Identifier used in URLs.")
    name: str = Field(examples=["Juan Carlos I"])
    aemet_id: str = Field(examples=["89064"], description="Identifier used by AEMET.")
    aemet_name: str = Field(
        examples=["JCI Estacion meteorologica"], description="Name returned by AEMET."
    )
    latitude: float
    longitude: float
    altitude_m: float
    timezone: str = Field(
        examples=["UTC-03:00"], description="Local time used for daily and monthly buckets."
    )
    available_range: TimeSpanOut | None = Field(
        default=None,
        description=(
            "Demo mode only: first and last recorded observation, in Europe/Madrid. "
            "Null when the data source cannot tell (real AEMET data)."
        ),
    )


class StationRef(BaseModel):
    id: str
    name: str
    aemet_id: str
    aemet_name: str


class FieldInfo(BaseModel):
    label: str = Field(description="Official dataset field name, used in CSV headers.")
    unit: str | None = None


class MeasurementRow(BaseModel):
    """One row. Only the requested measurements and, for aggregated rows, the quality fields appear.

    A measurement present with ``null`` means "no data"; an absent key means "not requested".
    """

    station: str = Field(examples=["Juan Carlos I"])
    datetime: str = Field(
        examples=["2026-03-29T05:00:00+02:00"],
        description="Observation time or bucket start, in Europe/Madrid with its UTC offset.",
    )
    period: str | None = Field(
        default=None,
        examples=["2026-03-29"],
        description="Station-local day or month of daily and monthly rows.",
    )
    temperature_c: float | None = None
    pressure_hpa: float | None = None
    speed_ms: float | None = None
    speed_cubic_mean_ms: float | None = Field(
        default=None,
        description="With `metrics=extended`: cube root of the mean of the cubed speeds.",
    )
    speed_max_ms: float | None = Field(
        default=None,
        description="With `metrics=extended`: highest ten-minute mean speed (not a gust).",
    )
    temperature_min_c: float | None = Field(
        default=None, description="With `metrics=extended`: lowest ten-minute mean temperature."
    )
    temperature_max_c: float | None = Field(
        default=None, description="With `metrics=extended`: highest ten-minute mean temperature."
    )
    air_density_kgm3: float | None = Field(
        default=None,
        description="With `metrics=extended`: mean density of dry air, p / (R·T), in kg/m³.",
    )
    power_density_wm2: float | None = Field(
        default=None,
        description=(
            "With `metrics=extended`: mean of ½·rho·v³ over the observations that have speed, "
            "temperature and pressure, in W/m²."
        ),
    )
    samples: int | None = Field(default=None, description="Observations used in the bucket.")
    expected_samples: int | None = Field(
        default=None, description="Ten-minute slots in a complete bucket."
    )
    coverage: float | None = Field(
        default=None, description="samples / expected_samples, as a percentage."
    )


class CacheInfo(BaseModel):
    status: Literal["hit", "miss", "partial"] = Field(
        description=(
            "`hit`: nothing had to be fetched from the data source; `miss`: every month of the "
            "range was fetched for this request; `partial`: a mix. Also sent as `X-Cache-Status`."
        )
    )
    last_updated: str | None = Field(
        examples=["2026-11-15T13:00:00+01:00"],
        description=(
            "When the months of the range that can still change (the current month, or one "
            "that ended recently) were fetched, the oldest of them, in Europe/Madrid. Null when "
            "all the requested data is final."
        ),
    )
    stale: bool = Field(
        description=(
            "True when a month that should have been refreshed is served from an older copy "
            "because AEMET failed; `last_updated` then tells how old it is. Also sent as "
            "`X-Data-Stale`."
        )
    )


class ResponseMetadata(BaseModel):
    station: StationRef
    aggregation: Aggregation
    start: str = Field(description="Interpreted start of the range, in Europe/Madrid.")
    end: str = Field(description="Interpreted end of the range (inclusive), in Europe/Madrid.")
    input_interpretation: str = Field(
        examples=["Europe/Madrid (default)"], description="How start and end were interpreted."
    )
    output_timezone: str = Field(examples=["Europe/Madrid"])
    station_timezone: str = Field(examples=["UTC-03:00"])
    source: Literal["aemet", "demo"] = Field(description="Where the data came from.")
    cache: CacheInfo = Field(description="Whether the data was served from the cache.")
    count: int = Field(description="Number of rows in data.")
    notice: str | None = Field(
        default=None,
        description="Explanation when no observation was found for the range (absent otherwise).",
    )


class MeasurementsResponse(BaseModel):
    metadata: ResponseMetadata
    fields: dict[str, FieldInfo] = Field(
        description="Official label and unit of every key present in the data rows."
    )
    data: list[MeasurementRow]


class AggregationOut(BaseModel):
    id: Aggregation = Field(description="Value of the `aggregation` parameter.")
    max_range_days: int | None = Field(
        examples=[31],
        description=(
            "Longest range accepted at this level, in days of real elapsed time: `end - start` "
            "must not exceed `max_range_days` x 24 hours. Null means no limit. A range of N "
            "calendar days in local time that crosses a daylight saving time change lasts N "
            "days plus or minus one hour, so it can be rejected (autumn) or accepted although "
            "the dates suggest it is longer (spring)."
        ),
    )


class MeasurementTypeOut(BaseModel):
    id: MeasurementType = Field(description="Value accepted by the `types` parameter.")
    key: str = Field(examples=["temperature_c"], description="Key of the measurement in rows.")
    label: str = Field(
        examples=["Temperature (°C)"],
        description="Official dataset field name, used in CSV headers and in the user interface.",
    )
    unit: str = Field(examples=["°C"])


class WindMetricOut(BaseModel):
    id: WindMetric
    key: str = Field(description="Key of the metric in rows.", examples=["power_density_wm2"])
    label: str = Field(examples=["Wind power density (W/m²)"])
    unit: str = Field(examples=["W/m²"])
    inputs: list[MeasurementType] = Field(
        description="Measurement types the metric needs; it is returned only if all are requested."
    )


class MetaResponse(BaseModel):
    source: Literal["aemet", "demo"] = Field(
        description="Where this deployment reads its data from: AEMET OpenData or recorded data."
    )
    output_timezone: str = Field(
        examples=["Europe/Madrid"], description="Time zone of every datetime in responses."
    )
    default_input_timezone: str = Field(
        examples=["Europe/Madrid"],
        description="Time zone of `start` and `end` when they have no offset and no `tz` is given.",
    )
    aggregations: list[AggregationOut] = Field(description="Levels, from finest to coarsest.")
    measurement_types: list[MeasurementTypeOut]
    wind_metrics: list[WindMetricOut] = Field(
        description="Returned with `metrics=extended` on hourly, daily and monthly rows."
    )


class ErrorDetail(BaseModel):
    code: str = Field(examples=["invalid_parameter"])
    message: str
    parameter: str | None = Field(default=None, examples=["start"])


class ErrorResponse(BaseModel):
    error: ErrorDetail
