"""Unit tests for measurement types and their presentation."""

from app.domain.measurements import (
    DATETIME_LABEL,
    MEASUREMENT_FIELDS,
    STATION_LABEL,
    Aggregation,
    MeasurementType,
)

DEGREE_SIGN = "°"
ORDINAL_INDICATOR = "º"  # looks almost identical, but it is the "o" of "1º"


def test_every_measurement_type_has_a_field_definition() -> None:
    assert set(MEASUREMENT_FIELDS) == set(MeasurementType)


def test_json_keys_and_labels_are_unique() -> None:
    fields = MEASUREMENT_FIELDS.values()

    assert len({field.key for field in fields}) == len(fields)
    assert len({field.label for field in fields}) == len(fields)


def test_official_labels_use_correct_unit_symbols() -> None:
    labels = {kind: field.label for kind, field in MEASUREMENT_FIELDS.items()}

    assert labels == {
        MeasurementType.TEMPERATURE: f"Temperature ({DEGREE_SIGN}C)",
        MeasurementType.PRESSURE: "Pressure (hPa)",
        MeasurementType.SPEED: "Speed (m/s)",
    }
    assert ORDINAL_INDICATOR not in labels[MeasurementType.TEMPERATURE]
    assert (STATION_LABEL, DATETIME_LABEL) == ("Station", "Datetime")


def test_fields_map_to_aemet_names() -> None:
    aemet_names = {kind: field.aemet_name for kind, field in MEASUREMENT_FIELDS.items()}

    assert aemet_names == {
        MeasurementType.TEMPERATURE: "temp",
        MeasurementType.PRESSURE: "pres",
        MeasurementType.SPEED: "vel",
    }


def test_aggregation_values_match_the_public_api() -> None:
    assert [level.value for level in Aggregation] == ["none", "hourly", "daily", "monthly"]
