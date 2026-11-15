"""Application error hierarchy.

Code raises these domain-level errors; the HTTP layer translates them into responses in a single
place, so changing how an error is presented never requires touching business logic.
"""


class AppError(Exception):
    """Base class for errors that the API reports to clients in a controlled way."""


class NotFoundError(AppError):
    """A requested resource does not exist."""


class UnknownStationError(NotFoundError):
    """The requested station identifier is not in the station registry."""

    def __init__(self, station_id: str, valid_ids: tuple[str, ...]) -> None:
        self.station_id = station_id
        self.valid_ids = valid_ids
        super().__init__(f"Unknown station '{station_id}'. Valid stations: {', '.join(valid_ids)}.")
