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


class InvalidParameterError(AppError):
    """A request parameter is malformed or inconsistent with the others."""

    def __init__(self, parameter: str, message: str) -> None:
        self.parameter = parameter
        self.message = message
        super().__init__(f"{parameter}: {message}")


class NonExistentLocalTimeError(InvalidParameterError):
    """A local time that the clocks skip when daylight saving time starts."""


class AmbiguousLocalTimeError(InvalidParameterError):
    """A local time that occurs twice when daylight saving time ends."""


class RangeTooLargeError(InvalidParameterError):
    """The requested range exceeds the maximum allowed for the aggregation level."""


class UpstreamError(AppError):
    """AEMET answered with an error or with a response that cannot be understood."""


class UpstreamUnavailableError(UpstreamError):
    """AEMET cannot be reached or is rate limiting us, even after retrying."""


class UpstreamTimeoutError(UpstreamError):
    """AEMET did not answer in time, even after retrying."""


class UpstreamCoolingDownError(UpstreamUnavailableError):
    """AEMET failed recently, so it is not called again until a cool-down period ends."""

    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            "AEMET failed recently and is not being called for a while. "
            f"Try again in {retry_after_seconds} seconds."
        )
