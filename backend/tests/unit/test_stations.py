"""Unit tests for the station registry."""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import UnknownStationError
from app.domain.stations import ANTARCTIC_STATION_TIME, STATIONS, get_station


def test_registry_maps_stations_to_verified_aemet_identifiers() -> None:
    assert {station.id: station.aemet_id for station in STATIONS.values()} == {
        "juan-carlos-i": "89064",
        "gabriel-de-castilla": "89070",
    }


def test_get_station_returns_the_registered_station() -> None:
    station = get_station("gabriel-de-castilla")

    assert station.name == "Gabriel de Castilla"
    assert station.aemet_name == "GdC Estacion meteorologica"


def test_unknown_station_error_lists_the_valid_identifiers() -> None:
    with pytest.raises(UnknownStationError) as excinfo:
        get_station("89064")

    assert excinfo.value.station_id == "89064"
    assert "juan-carlos-i" in str(excinfo.value)
    assert "gabriel-de-castilla" in str(excinfo.value)


@pytest.mark.parametrize(
    "instant",
    [
        datetime(2025, 1, 15, 12, tzinfo=UTC),  # austral summer
        datetime(2025, 3, 30, 1, tzinfo=UTC),  # Madrid DST change
        datetime(2015, 7, 1, 12, tzinfo=UTC),  # austral winter, before 2016
    ],
)
def test_station_local_time_is_always_utc_minus_three(instant: datetime) -> None:
    assert ANTARCTIC_STATION_TIME.utcoffset(instant) == timedelta(hours=-3)
    assert ANTARCTIC_STATION_TIME.tzname(instant) == "UTC-03:00"
