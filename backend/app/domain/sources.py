"""The port through which the application obtains observations, whatever their origin."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.measurements import Observation
from app.domain.stations import Station


@dataclass(frozen=True, slots=True)
class AvailableRange:
    """First and last observation a source holds for a station (aware UTC datetimes)."""

    start: datetime
    end: datetime


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


@runtime_checkable
class KnowsAvailableRange(Protocol):
    """Optional capability of sources that know in advance which data they hold.

    The recorded (demo) source has it; the AEMET client does not, since finding out would require
    extra upstream calls. ``isinstance(source, KnowsAvailableRange)`` tells them apart at runtime.
    """

    def available_range(self, station: Station) -> AvailableRange | None:
        """Return the span of the data held for ``station``, or ``None`` if there is none."""
        ...
