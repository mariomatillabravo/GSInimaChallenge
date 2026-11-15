"""Weather source that replays recorded AEMET data, so the application runs without an API key."""

from datetime import datetime
from pathlib import Path

from app.clients.aemet_parser import decode_body, parse_observations
from app.domain.chunks import month_chunks
from app.domain.measurements import Observation
from app.domain.sources import AvailableRange
from app.domain.stations import Station


class RecordedWeatherSource:
    """``WeatherSource`` backed by recorded AEMET responses (demo mode).

    The directory holds one file per station and month, named ``{aemet_id}_{YYYY-MM}.json``,
    containing the data array of that month exactly as AEMET serves it (possibly trimmed to the
    fields the application uses). The files go through the same parser as live responses, so
    demo mode exercises the real parsing and cleaning code.
    """

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        # The files never change while the application runs, so each range is computed once.
        self._ranges: dict[str, AvailableRange | None] = {}

    def fetch(self, station: Station, start: datetime, end: datetime) -> list[Observation]:
        """Return the recorded observations in ``[start, end]``; months without a file are empty."""
        observations: list[Observation] = []
        for chunk in month_chunks(start, end):
            path = self._directory / f"{station.aemet_id}_{chunk.key}.json"
            if path.is_file():  # a month without a file behaves like AEMET's "no data" answer
                observations.extend(
                    obs for obs in self._read(path) if start <= obs.timestamp <= end
                )
        return observations

    def available_range(self, station: Station) -> AvailableRange | None:
        """First and last recorded observation of ``station``, or ``None`` without recordings."""
        if station.aemet_id not in self._ranges:
            timestamps = [
                obs.timestamp
                for path in sorted(self._directory.glob(f"{station.aemet_id}_*.json"))
                for obs in self._read(path)
            ]
            self._ranges[station.aemet_id] = (
                AvailableRange(start=min(timestamps), end=max(timestamps)) if timestamps else None
            )
        return self._ranges[station.aemet_id]

    @staticmethod
    def _read(path: Path) -> list[Observation]:
        return parse_observations(decode_body(path.read_bytes(), "utf-8")).observations
