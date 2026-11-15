"""Circuit breaker: stop calling a failing data source for a while."""

import logging
import math
import threading
from datetime import datetime, timedelta
from typing import Final

from app.core.clock import Clock

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN: Final = timedelta(seconds=60)


class CircuitBreaker:
    """Opens after a failed fetch and stays open for a cool-down period.

    A failed fetch has already been retried by the client, so one failure means the source is
    really unavailable. While the circuit is open nobody calls the source: callers serve cached
    copies at once or fail fast, instead of each waiting for a new round of retries. Once the
    cool-down ends, the next fetch is attempted again: success closes the circuit and failure
    opens it for another period.

    The state lives in the process and is shared by all its threads.
    """

    def __init__(self, cooldown: timedelta, clock: Clock) -> None:
        self._cooldown = cooldown
        self._clock = clock
        self._lock = threading.Lock()
        self._open_until: datetime | None = None

    def retry_after_seconds(self) -> int | None:
        """Whole seconds until the source may be called again, or ``None`` if it may be now."""
        with self._lock:
            if self._open_until is None:
                return None
            remaining = (self._open_until - self._clock()).total_seconds()
        return math.ceil(remaining) if remaining > 0 else None

    def record_success(self) -> None:
        with self._lock:
            was_open = self._open_until is not None
            self._open_until = None
        if was_open:
            logger.info("The data source answered again; calls are back to normal.")

    def record_failure(self) -> None:
        with self._lock:
            self._open_until = self._clock() + self._cooldown
        logger.warning(
            "The data source failed; it will not be called for %d seconds.",
            self._cooldown.total_seconds(),
        )
