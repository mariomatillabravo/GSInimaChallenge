"""The current time, behind a function type so that tests can control it."""

from collections.abc import Callable
from datetime import UTC, datetime

Clock = Callable[[], datetime]
"""Returns the current time, aware and in UTC."""


def utc_now() -> datetime:
    return datetime.now(UTC)
