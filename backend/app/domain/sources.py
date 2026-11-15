"""The port through which the application obtains observations, whatever their origin."""

from datetime import datetime
from typing import Protocol

from app.domain.measurements import Observation
from app.domain.stations import Station


class WeatherSource(Protocol):
    """Anything that can provide the observations of a station for a time range.

    Implementations: the AEMET Antarctica client (real data) and the recorded source (demo mode).
    Tests use simple fakes. Any class with a matching ``fetch`` method satisfies the protocol; no
    inheritance is needed.
    """

    def fetch(self, station: Station, start: datetime, end: datetime) -> list[Observation]:
        """Return the cleaned observations with ``start <= timestamp <= end``, sorted by time.

        An empty list means that there is no data for the range; it is not an error.

        Raises:
            UpstreamError: If the data cannot be obtained.
        """
        ...
