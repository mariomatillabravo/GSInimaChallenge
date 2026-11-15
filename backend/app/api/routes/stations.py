"""Supporting endpoint: the stations the API can query."""

from fastapi import APIRouter

from app.api.presenters import present_station
from app.api.schemas import StationOut
from app.domain.stations import STATIONS

router = APIRouter(prefix="/api/v1", tags=["stations"])


@router.get("/stations", summary="List the available stations")
def list_stations() -> list[StationOut]:
    """Stations that can be used in ``/api/v1/stations/{station_id}/measurements``."""
    return [present_station(station) for station in STATIONS.values()]
