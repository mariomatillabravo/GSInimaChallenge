"""Response schemas: the public contract of the API, also used to generate the OpenAPI document."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.measurements import Aggregation


class OutputFormat(StrEnum):
    JSON = "json"
    CSV = "csv"


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
    samples: int | None = Field(default=None, description="Observations used in the bucket.")
    expected_samples: int | None = Field(
        default=None, description="Ten-minute slots in a complete bucket."
    )
    coverage: float | None = Field(
        default=None, description="samples / expected_samples, as a percentage."
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
    count: int = Field(description="Number of rows in data.")


class MeasurementsResponse(BaseModel):
    metadata: ResponseMetadata
    fields: dict[str, FieldInfo] = Field(
        description="Official label and unit of every key present in the data rows."
    )
    data: list[MeasurementRow]


class ErrorDetail(BaseModel):
    code: str = Field(examples=["invalid_parameter"])
    message: str
    parameter: str | None = Field(default=None, examples=["start"])


class ErrorResponse(BaseModel):
    error: ErrorDetail
