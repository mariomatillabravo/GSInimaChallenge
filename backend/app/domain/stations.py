"""Registry of the supported meteorological stations.

Stations are data, not code: adding another station served by the same AEMET endpoint is a new
entry in ``STATIONS``. A station network served by a different AEMET endpoint would need a new
data-source adapter as well.
"""

from dataclasses import dataclass
from datetime import timedelta, timezone, tzinfo
from types import MappingProxyType
from typing import Final

from app.core.exceptions import UnknownStationError

ANTARCTIC_STATION_TIME: Final = timezone(timedelta(hours=-3), "UTC-03:00")
"""Local time used to cut station days and months.

The Spanish Antarctic bases operate seasonally (roughly November to March) in a region that uses
UTC-03:00 all year round. A fixed offset keeps every station day exactly 24 hours long. The clock
actually used at the bases is still to be verified, which is why it is configurable per station.
"""


@dataclass(frozen=True, slots=True)
class Station:
    """A meteorological station and everything needed to query and present its data."""

    id: str
    """URL-friendly identifier used by this API."""
    name: str
    """Display name used in responses, CSV exports and the user interface."""
    aemet_id: str
    """Identifier expected by the AEMET endpoint."""
    aemet_name: str
    """Name returned by AEMET in the ``nombre`` field, kept for traceability."""
    local_timezone: tzinfo
    """Time zone that defines station-local days and months for aggregation."""
    latitude: float
    longitude: float
    altitude_m: float


STATIONS: Final[MappingProxyType[str, Station]] = MappingProxyType(
    {
        station.id: station
        for station in (
            Station(
                id="juan-carlos-i",
                name="Juan Carlos I",
                aemet_id="89064",
                aemet_name="JCI Estacion meteorologica",
                local_timezone=ANTARCTIC_STATION_TIME,
                latitude=-62.66325,
                longitude=-60.38959,
                altitude_m=12.0,
            ),
            Station(
                id="gabriel-de-castilla",
                name="Gabriel de Castilla",
                aemet_id="89070",
                aemet_name="GdC Estacion meteorologica",
                local_timezone=ANTARCTIC_STATION_TIME,
                latitude=-62.97697,
                longitude=-60.67528,
                altitude_m=12.0,
            ),
        )
    }
)


def get_station(station_id: str) -> Station:
    """Return the station with the given API identifier.

    Raises:
        UnknownStationError: If the identifier is not in the registry.
    """
    try:
        return STATIONS[station_id]
    except KeyError:
        raise UnknownStationError(station_id, valid_ids=tuple(STATIONS)) from None
